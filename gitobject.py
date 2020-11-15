

"""
The classes in this module allow managing git objects in .git/objects
"""
import hashlib
import zlib
import re
import os
from abc import ABCMeta, abstractmethod


class GitObjectManager(object):

    def __init__(self, git_root):
        self.git_root = git_root
        self.git_objects_path = os.path.join(git_root, "objects")
        self.obj_file_list = []
        pattern = re.compile(r'^[0-9a-fA-F]{38}$')
        for root, dirs, files in os.walk(self.git_objects_path, topdown=False):
            for name in files:
                if pattern.match(name):
                    file_name = os.path.join(root, name)
                    self.obj_file_list.append(file_name)
        for file_name in self.obj_file_list:
            with open(file_name, "rb") as f:
                obj_content = f.read()
            git_obj = GitBlobObject.from_obj(obj_content)
            print(git_obj)

    @staticmethod
    def sha1_to_path(sha1):
        # TODO: parameterize the path blow, it should refers to .git/objects
        # so may be this method shouldn't be static
        return os.path.join("./data/git_test_proj_1/git/objects", sha1[:2], sha1[2:])


class GitObject(object):
    __metaclass__ = ABCMeta

    def __init__(self, obj_content=None, raw_content=None, obj_type=None, encode="utf8"):
        """
        __init__
        :param obj_content:
            the content bytes of object file
        :param raw_content:
            decompressed witout header, a header looks like b"blob 10\x00", 
            for different types of objects, it may be slightly different
        :obj_type:
            one of types of object file -- "blob", "tree" or "commit"
        :encode: 
            encode for encoding and decoding object files, defalut is "utf8"
        """
        
        # self.raw_content:bytes
        # decompressed witout header, a header looks like b"blob 10\x00"
        # for different types of objects, it may be slightly different
        self.raw_content = None 
        
        # self.sha1:str
        # for the object file name -- self.sha1[:2] + os.sep + self.sha[2:]
        self.sha1 = None
        
        # self.obj_content:bytes
        # the content of object file
        self.obj_content = None
        
        # self.raw_content_length:int
        # length in header, a header looks like b"blob " + str(length).encode(self.encode) + b"\x00"
        self.raw_content_length = None
        
        # self.encode:str
        # encode for encoding and decoding object files, defalut is "utf8"
        self.encode = encode
        
        # self.type:str
        # one of types of object file -- "blob", "tree" or "commit"
        self.type = obj_type
        
        if raw_content is not None:
            self.raw_content = raw_content
            self.__to_obj()
        elif obj_content is not None:
            self.obj_content = obj_content
            self.__to_workspace()
        else:
            raise Exception("obj_content or raw_content not specified")

    @abstractmethod
    def decode_obj_content(self, obj_content_bytes):
        """
        decode obj content to raw content, for human understanding
        don't forget to set members if necessary
        :param obj_content_bytes: 
            bytes without head
        :return: 
            bytes that can decode by self.decode
        """
        raise NotImplementedError("decode_obj_content")

    @abstractmethod
    def encode_raw_content(self, **kwarg):
        """
        encode raw content to git obj content
        :param kwarg: 
            members to provide info
        :return: 
            bytes that can save to an obj file
        """
        raise NotImplementedError("encode_raw_content")

    @staticmethod
    def get_type(obj_content):
        decompressed = zlib.decompress(obj_content)

        decompress_list = decompressed.split(b"\x00", maxsplit=1)
        header_str = decompress_list[0].decode("ascii")
        pattern = re.compile(r"(blob|tree|commit) (\d+)")
        header_match = re.match(pattern, header_str)
        if header_match is None:
            raise ValueError("obj_content error")
        return header_match.group(1)

    @staticmethod
    def from_obj(obj_content):
        type_str = GitObject.get_type(obj_content)
        if type_str == "blob":
            return GitBlobObject(obj_content)
        elif type_str == "tree":
            return GitTreeObject(obj_content)
        elif type_str == "commit":
            return GitCommitObject(obj_content)
        else:
            raise ValueError("type mismatch")

    @staticmethod
    def from_raw(raw_content, type_str):
        if type_str == "blob":
            return GitBlobObject(raw_content=raw_content)
        elif type_str == "tree":
            return GitTreeObject(raw_content=raw_content)
        elif type_str == "commit":
            return GitCommitObject(raw_content=raw_content)
        else:
            raise ValueError("type mismatch")

    def __to_workspace(self):
        """
        self.obj_content is known
        assign values to self.raw_content, self.sha1 and etc based on self.raw_content
        """
        decompressed = zlib.decompress(self.obj_content)
        self.sha1 = hashlib.sha1(decompressed).hexdigest()

        decompress_list = decompressed.split(b"\x00", maxsplit=1)
        header_str = decompress_list[0].decode(self.encode)
        pattern = re.compile(r"(blob|tree|commit) (\d+)")
        header_match = re.match(pattern, header_str)
        if header_match is None:
            raise Exception("obj_content error")
        if self.type is not None and self.type != header_match.group(1):
            raise Exception("type mismatch")
        self.raw_content = self.decode_obj_content(decompress_list[1])
        self.raw_content_length = int(header_match.group(2))

    def __to_obj(self):
        """
        self.raw_content, self.type, et al are known
        assign values to self.obj_content, self.sha1 and etc based on self.raw_content
        """
        encoded = self.raw_content.encode(self.encode)
        self.raw_content_length = len(encoded)
        content_str = "%s %d\x00%s" % (self.type, self.raw_content_length, encoded)
        content_byte = content_str.encode(self.encode)
        self.sha1 = hashlib.sha1(content_byte).hexdigest()
        self.obj_content = zlib.compress(content_byte)
        # self.obj_file_name = self.sha1[:2] + "/" + self.sha1[2:]

    def save_as_obj(self, file_name):
        with open(file_name, "wb") as f:
            f.write(self.obj_content)

    def save_as_raw(self, file_name):
        with open(file_name, "wb") as f:
            f.write(self.raw_content.encode(self.encode))

    def __eq__(self, other):
        return self.sha1 == other.sha1

    def __str__(self):
        return "[{} {} {} {}]:{}".format(self.__class__.__name__, self.type, self.raw_content_length, self.sha1[:4],
                                         self.raw_content.decode(self.encode).replace("\n", " "))


class GitBlobObject(GitObject):
    # TODO: implement method encode_raw_content
    def __init__(self, obj_content=None, raw_content=None, encode="utf8"):
        super(GitBlobObject, self).__init__(obj_content, raw_content, obj_type="blob", encode=encode)

    def decode_obj_content(self, obj_content_bytes):
        return obj_content_bytes


class GitTreeObject(GitObject):
    # TODO: implement method encode_raw_content
    def __init__(self, obj_content=None, raw_content=None, encode="utf8"):
        self.file_dict = {}
        super(GitTreeObject, self).__init__(obj_content, raw_content, obj_type="tree", encode=encode)

    def decode_obj_content(self, obj_content_bytes):
        pattern = re.compile(b"(\\d{6}) (.+?)\x00([\x00-\xff]{20})")
        lines_list = re.findall(pattern, obj_content_bytes)
        line_str_list = []
        for mod, file_name, sha1 in lines_list:
            sha1_hex_str = sha1.hex()
            file_path = GitObjectManager.sha1_to_path(sha1_hex_str)
            with open(file_path, "rb") as f:
                obj_type_str = GitObject.get_type(f.read())
            mod_str, file_name_str = mod.decode(self.encode), file_name.decode(self.encode)
            self.file_dict[sha1_hex_str] = (mod_str, obj_type_str, file_name_str)
            line_str_list.append("{}\t{}\t{}\t{}\n".format(mod_str, obj_type_str, sha1_hex_str, file_name_str))
        return "\n".join(line_str_list).encode(self.encode)


class GitCommitObject(GitObject):
    # TODO: implement method encode_raw_content
    def __init__(self, obj_content=None, raw_content=None, encode="utf8"):
        self.tree_sha1 = None
        self.parent_sha1_list = []
        self.author_name = None
        self.author_email = None
        self.author_time = None
        self.committer_name = None
        self.committer_email = None
        self.committer_time = None
        self.commit_message = None
        super(GitCommitObject, self).__init__(obj_content, raw_content, obj_type="commit", encode=encode)

    def decode_obj_content(self, obj_content_bytes):
        self.tree_sha1 = re.search(br"tree ([0-9a-zA-Z]{40})", obj_content_bytes).group(1).decode(self.encode)
        self.parent_sha1_list = re.findall(br"parent ([0-9a-zA-Z]{40})", obj_content_bytes)
        tmp = re.search(br"author (.+?) <(.+?)> (\d{10} [+-]\d{4})", obj_content_bytes).groups()
        self.author_name = tmp[0].decode(self.encode)
        self.author_email = tmp[1].decode(self.encode)
        self.author_time = tmp[2].decode(self.encode)
        tmp = re.search(br"committer (.+?) <(.+?)> (\d{10} [+-]\d{4})", obj_content_bytes).groups()
        self.committer_name = tmp[0].decode(self.encode)
        self.committer_email = tmp[1].decode(self.encode)
        self.committer_time = tmp[2].decode(self.encode)
        self.commit_message = re.search(b"\n\n(.+?)\n", obj_content_bytes).group(1)
        return obj_content_bytes


if __name__ == '__main__':
    GitObjectManager("./test_data/git/")
