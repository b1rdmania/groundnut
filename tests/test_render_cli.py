import json

from groundnut.render_cli import main


def test_render_cli_writes_receipt_and_fails_closed(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("Claim [source](https://example.test/a)\n")
    rendered = tmp_path / "rendered.html"
    rendered.write_text('<p>Claim <a href="https://example.test/a">source</a></p>')
    output = tmp_path / "receipt.json"

    assert (
        main(
            [
                "--source",
                str(source),
                "--rendered",
                str(rendered),
                "--renderer-name",
                "fixture",
                "--renderer-version",
                "1",
                "--out",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text())["parity"]["evidence_sequence_identical"]

    rendered.write_text("<p>Claim without source.</p>")
    assert (
        main(
            [
                "--source",
                str(source),
                "--rendered",
                str(rendered),
                "--renderer-name",
                "fixture",
                "--renderer-version",
                "1",
            ]
        )
        == 2
    )
