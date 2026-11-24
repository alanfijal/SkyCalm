from scripts.package_lambda import archive_bytes


def test_wheel_record_only_lists_files_in_the_zip(tmp_path):
    directory = tmp_path / "sample.dist-info"
    directory.mkdir()
    record = directory / "RECORD"
    members = {"sample/module.py", "sample.dist-info/RECORD"}
    expected = b"sample/module.py,sha256=abc,12\r\nsample.dist-info/RECORD,,\r\n"
    for script_hash in ("first-environment", "second-environment"):
        record.write_bytes(f"../../bin/tool,{script_hash},123\r\n".encode() + expected)
        assert archive_bytes(record, members) == expected
