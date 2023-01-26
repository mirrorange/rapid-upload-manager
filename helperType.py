class pathType:
    @staticmethod
    def path_from_str(path_s: str, **kwargs):
        if "absolute" in kwargs:
            absolute = kwargs["absolute"]
        else:
            absolute = path_s.startswith("/")
        path = path_s.strip("/").split("/")
        return pathType(path, absolute)

    basename: str
    path: list[str]
    absolute: bool

    def __init__(self, path: list[str], absolute: bool):
        self.path = path
        self.absolute = absolute
        self.simplify()

    def __repr__(self):
        path_s = "/".join(self.path)
        if self.absolute:
            path_s = "/" + path_s
        return path_s

    def __getitem__(self, index):
        return self.path[index]

    def __setitem__(self, index, key):
        self.path[index] = key

    def __len__(self):
        return len(self.path)

    def __add__(self, other):
        if other.absolute:
            return other
        else:
            return pathType(self.path + other.path, self.absolute)

    def __sub__(self, other):
        path1 = self.path.copy()
        path2 = other.path.copy()
        while path1 and path2 and path1[0] == path2[0]:
            path1.pop(0)
            path2.pop(0)
        return pathType([".."] * len(path2) + path1, False)

    def __contains__(self, other):
        rpath = other - self
        return len(rpath) == 0 or rpath[0] != ".."

    def __eq__(self, other):
        return self.path == other.path and self.absolute == other.absolute

    def __hash__(self) -> int:
        return hash(str(self))

    def simplify(self):
        tpath = []
        for p in self.path:
            if p == "." or p == "":
                continue
            elif p == "..":
                if tpath and tpath[-1] != "..":
                    tpath.pop()
                elif not self.absolute:
                    tpath.append("..")
            else:
                tpath.append(p)
        self.path = tpath

    def get_basename(self):
        return self.path[-1] if self.path else ""

    def get_dirname(self):
        return self + pathType([".."], False)

    basename = property(fget=get_basename)
    dirname = property(fget=get_dirname)


class itemType:

    name: str
    path: pathType
    type: int
    data: dict

    def __init__(self, path: pathType, type: int, data: dict):
        self.path = pathType(path, True)
        self.name = self.path.basename
        self.type = type
        self.data = data
