"""
The classes in this module allow managing git objects in .git/objects
"""
import hashlib
import zlib
import re
import os
from abc import abstractmethod
from datetime import datetime
import time
import configparser


class GitInfo(object):
    def __init__(self, workspace_path, **kwargs):
        self.workspace_path = workspace_path
        self.root_path = os.path.join(workspace_path, "git")
        self.obj_path = os.path.join(self.root_path, "objects")
        self.ref_path = os.path.join(self.root_path, "refs")
        self.hook_path = os.path.join(self.root_path, "hooks")
        self.info_path = os.path.join(self.root_path, "info")
        self.log_path = os.path.join(self.root_path, "logs")
        self.git_ignore_filename = os.path.join(self.workspace_path, ".gitignore")
        self.config_filename = os.path.join(self.root_path, "config")

        self.cp = configparser.ConfigParser()
        self.cp.read(self.config_filename)
        self.author = self.cp.get("user", "name")
        self.author_email = self.cp.get("user", "email")
        self.committer = self.cp.get("user", "name")
        self.committer_email = self.cp.get("user", "email")

        self.filtered_list = [self.root_path, self.git_ignore_filename]
        # TODO: 实现gitignore， 注意修改is_filtered

    def sha1_to_obj_filename(self, sha1):
        obj_file_dir = os.path.join(self.obj_path, sha1[:2])
        return obj_file_dir, os.path.join(obj_file_dir, sha1[2:])

    def filename_from_workspace_to_full(self, filename_from_workspace):
        return os.path.join(self.workspace_path, filename_from_workspace)

    def is_filtered(self, filename_from_workspace):
        for filter_path in self.filtered_list:
            if GitInfo.is_path_equal(self.filename_from_workspace_to_full(filename_from_workspace), filter_path):
                return True

    @classmethod
    def is_path_equal(cls, path_a, path_b):
        return os.path.normpath(os.path.normcase(os.path.abspath(path_a))) == os.path.normpath(
            os.path.normcase(os.path.abspath(path_b)))


class GitObject(object):

    def __init__(self, git_info: GitInfo):

        self.git_info = git_info

        # decompressed without header, a header looks like b"blob 10\x00"
        self.body_content = None

        # self.sha1:str
        self.sha1 = None

        # self.obj_content:bytes
        # the decompressed content of object file
        self.full_content = None

        # self.raw_content_length:int
        # length value in header, a header looks like b"blob " + str(self.len).encode(self.encode) + b"\x00"
        self.len = None

        # self.type:str
        # one of types of object file -- "blob", "tree" or "commit"
        self.type = None

    def set_general_from_body_content(self):
        self.len = len(self.body_content)
        self.full_content = self.type.encode("ascii") + b" " + str(self.len).encode(
            "ascii") + b"\x00" + self.body_content
        self.sha1 = hashlib.sha1(self.full_content).hexdigest()

    def save_obj(self):
        obj_file_dir, obj_filename = self.git_info.sha1_to_obj_filename(self.sha1)
        os.makedirs(obj_file_dir)
        with open(obj_filename, "wb") as f:
            f.write(zlib.compress(self.full_content))

    def from_obj(self, content: bytes = None, filename_sha1: str = None):
        if (content is None and filename_sha1 is None) or (content is not None and filename_sha1 is not None):
            raise AssertionError("one of content and filename_sha1 should be set")
        if content is None:
            _, obj_filename = self.git_info.sha1_to_obj_filename(filename_sha1)
            with open(obj_filename, "rb") as f:
                content = f.read()

        self.full_content = zlib.decompress(content)
        pattern = re.compile(b"^(blob|tree|commit) (\\d+)\x00([\x00-\xff]*)$")
        match = re.search(pattern, self.full_content)
        if match is None:
            raise ValueError("object file format illegal")
        if self.type is None or self.type != match.group(1).decode("ascii"):
            raise AssertionError("type mismatch")
        self.type, self.len = match.group(1).decode("ascii"), int(match.group(2).decode("ascii"))
        self.body_content = match.group(3)
        self.sha1 = hashlib.sha1(self.full_content).hexdigest()
        if filename_sha1 is not None and filename_sha1 != self.sha1:
            raise AssertionError("calculated sha1 not equal to the given filename_sha1")
        self.set_unique_from_body_content()

        return self

    @abstractmethod
    def from_workspace(self):
        raise NotImplementedError("from_workspace")

    @abstractmethod
    def set_unique_from_body_content(self):
        raise NotImplementedError("set_unique_from_body_content")

    @abstractmethod
    def get_display(self):
        raise NotImplementedError("get_display")

    def __eq__(self, other):
        return self.sha1 == other.sha1

    def __hash__(self):
        hash(self.sha1)

    def __str__(self):
        return f"=========={self.__class__.__name__} {self.type} {self.len} {self.sha1[:4]}" \
               f"==========\n{self.get_display()}\n===========================\n\n "


class GitBlobObject(GitObject):
    def __init__(self, git_info: GitInfo):
        super(GitBlobObject, self).__init__(git_info)
        self.type = "blob"

    def from_workspace(self, content: bytes = None, filename_from_workspace: str = None):
        if (content is None and filename_from_workspace is None) or (
                content is not None and filename_from_workspace is not None):
            raise AssertionError("one of content and filename_from_git should be set")
        if content is None:
            with open(self.git_info.filename_from_workspace_to_full(filename_from_workspace), "rb") as f:
                content = f.read()

        self.body_content = content.replace(b"\r\n", b"\n")
        self.type = "blob"
        self.set_general_from_body_content()

        return self

    def get_display(self):
        if self.body_content is not None:
            return self.body_content.decode("utf8")
        else:
            raise ValueError("body_content not set")

    def set_unique_from_body_content(self):
        pass


class GitTreeObject(GitObject):
    def __init__(self, git_info: GitInfo):
        super(GitTreeObject, self).__init__(git_info)
        self.type = "tree"
        self.mod_filename_sha1_list = None

    def from_workspace(self, mod_filename_sha1_list: list = None, dirname_from_workspace: str = None):
        if (mod_filename_sha1_list is None and dirname_from_workspace is None) or (
                mod_filename_sha1_list is not None and dirname_from_workspace is not None):
            raise AssertionError("one of mod_filename_sha1_list and dir_name_from_workspace should be set")
        if dirname_from_workspace is not None:
            mod_filename_sha1_list = []
            files = os.listdir(self.git_info.filename_from_workspace_to_full(dirname_from_workspace))
            for fi in files:
                filename = os.path.join(dirname_from_workspace, fi)
                if self.git_info.is_filtered(filename):
                    continue
                if os.path.isdir(self.git_info.filename_from_workspace_to_full(filename)):
                    gto_tmp = GitTreeObject(self.git_info)
                    gto_tmp.from_workspace(dirname_from_workspace=filename)
                    mod_filename_sha1_list.append(("40000", fi, gto_tmp.sha1))
                    del gto_tmp
                else:
                    gbo_tmp = GitBlobObject(self.git_info)
                    gbo_tmp.from_workspace(filename_from_workspace=filename)
                    mod_filename_sha1_list.append(("100644", fi, gbo_tmp.sha1))
                    del gbo_tmp

        self.mod_filename_sha1_list = mod_filename_sha1_list
        tmp_list = []
        for mod, filename, sha1 in mod_filename_sha1_list:
            tmp_list.append(b"%s %s\x00%s" % (mod.encode("ascii"), filename.encode("utf8"), bytes.fromhex(sha1)))
        self.body_content = b"".join(tmp_list)
        self.type = "tree"
        self.set_general_from_body_content()

        return self

    def get_display(self):
        if self.mod_filename_sha1_list is not None:
            tmp_list = []
            for mod, filename, sha1 in self.mod_filename_sha1_list:
                tmp_list.append(f"{mod}\t{filename}\t\t{sha1}")
            return "\n".join(tmp_list)
        else:
            raise ValueError("mod_filename_sha1_list not set, call from_workspace or from_obj first")

    def set_unique_from_body_content(self):
        pattern = re.compile(b"(\\d+?) (.+?)\x00([\x00-\xff]{20})")
        lines_list = re.findall(pattern, self.body_content)
        if len(lines_list) == 0:
            raise AssertionError("mismatch format of a tree object")
        self.mod_filename_sha1_list = []
        for mod, filename, sha1 in lines_list:
            self.mod_filename_sha1_list.append((mod.decode("ascii"), filename.decode("utf8"), sha1.hex()))


class GitCommitObject(GitObject):
    def __init__(self, git_info: GitInfo):
        super(GitCommitObject, self).__init__(git_info)
        self.type = "commit"
        self.tree_sha1 = None
        self.parents_sha1_list = None
        self.author = None
        self.author_email = None
        self.author_time = None
        self.committer = None
        self.committer_email = None
        self.committer_time = None
        self.message = None

    def from_workspace(self, parents_sha1_list=None, commit_message=None):
        if parents_sha1_list is None:
            parents_sha1_list = []
        if commit_message is None:
            commit_message = ""
        gto = GitTreeObject(self.git_info).from_workspace(dirname_from_workspace=".")
        self.tree_sha1 = gto.sha1
        self.parents_sha1_list = parents_sha1_list
        self.author = self.git_info.author
        self.committer = self.git_info.author
        self.author_email = self.git_info.author_email
        self.author_time = f"{int(datetime.now().timestamp())} {time.strftime('%z')}"
        self.committer_email = self.git_info.committer_email
        self.committer_time = self.author_time
        self.message = commit_message

        tmp_list = [b"tree %s\n" % self.tree_sha1.encode("ascii")]
        for parent_sha1 in self.parents_sha1_list:
            tmp_list.append(b"parent %s\n" % parent_sha1.encode("ascii"))
        tmp_list.append(b"author %s <%s> %s\n" %
                        (self.author.encode("utf8"),
                         self.author_email.encode("utf8"),
                         self.author_time.encode("ascii")))
        tmp_list.append(b"committer %s <%s> %s\n" %
                        (self.committer.encode("utf8"),
                         self.committer_email.encode("utf8"),
                         self.committer_time.encode("ascii")))
        tmp_list.append(b"\n%s\n" % self.message.encode("utf8"))
        self.body_content = b"".join(tmp_list)
        self.set_general_from_body_content()

        return self

    def get_display(self):
        if self.body_content is not None:
            return self.body_content.decode("utf8")
        else:
            raise ValueError("body_content not set, call from_workspace or from_obj first")

    def set_unique_from_body_content(self):
        # TODO: 根据self.body_content设置self.tree_sha1,self.parents_sha1_list,self.author,self.author_email,
        #  self.author_time,self.committer,self.committer_email,self.committer_time,self.message
        # 上述变量都是字符串类型，具体格式参见self.body_content和self.from_workspace方法里的设置
        pass


if __name__ == '__main__':
    gi = GitInfo("./data/git_test_proj_2")
    gbo1 = GitBlobObject(git_info=gi)
    gbo1.from_obj(filename_sha1="9d6b5d44f22b003cb21fd4fcc379b489d2ef44d6")
    gbo2 = GitBlobObject(git_info=gi)
    gbo2.from_workspace(filename_from_workspace="中文.c")
    gto1 = GitTreeObject(git_info=gi)
    gto1.from_obj(filename_sha1="f4daa999bb7c4e0b1f45c9eab634bff8bb80ad93")
    gto2 = GitTreeObject(git_info=gi)
    gto2.from_workspace(dirname_from_workspace="folder1")
    gco1 = GitCommitObject(git_info=gi)
    gco1.from_obj(filename_sha1="0302aff7feaab0414fabbc2d0749975022b67fba")
    gco2 = GitCommitObject(git_info=gi)
    gco2.from_workspace(parents_sha1_list=["b97323d9ebc525e57817ad85a92f63b5a5d390c1"], commit_message="add 中文 folder")
    print(gbo1)
    print(gbo2)
    print(gto1)
    print(gto2)
    print(gco1)
    print(gco2)
