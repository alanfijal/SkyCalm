"""Read the two regular files produced by a SageMaker model artifact."""

import tarfile


def read_artifact(source):
    with tarfile.open(fileobj=source, mode="r:gz") as tar:
        members = tar.getmembers()

        def read(name, limit):
            matches = [m for m in members if m.name.removeprefix("./") == name]
            if len(matches) != 1 or not matches[0].isfile() or not 0 < matches[0].size <= limit:
                raise ValueError("Unexpected model artifact member")
            with tar.extractfile(matches[0]) as stream:
                return stream.read()

        return read("model.txt", 5_000_000), read("model.json", 2048)
