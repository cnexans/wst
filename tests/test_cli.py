from click.testing import CliRunner

from wst.cli import _copy_to_inbox, cli


class TestCopyToInbox:
    def test_copy_single_pdf(self, tmp_path):
        inbox = tmp_path / "inbox"
        source = tmp_path / "book.pdf"
        source.write_text("pdf content")

        count = _copy_to_inbox(source, inbox)
        assert count == 1
        assert (inbox / "book.pdf").exists()

    def test_ignores_non_pdf(self, tmp_path):
        inbox = tmp_path / "inbox"
        source = tmp_path / "notes.txt"
        source.write_text("text")

        count = _copy_to_inbox(source, inbox)
        assert count == 0

    def test_copy_directory_recursive(self, tmp_path):
        inbox = tmp_path / "inbox"
        src_dir = tmp_path / "docs"
        (src_dir / "sub").mkdir(parents=True)
        (src_dir / "a.pdf").write_text("a")
        (src_dir / "sub" / "b.pdf").write_text("b")
        (src_dir / "readme.txt").write_text("ignore")

        count = _copy_to_inbox(src_dir, inbox)
        assert count == 2

    def test_handles_name_collision(self, tmp_path):
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        (inbox / "book.pdf").write_text("existing")

        source = tmp_path / "book.pdf"
        source.write_text("new")

        count = _copy_to_inbox(source, inbox)
        assert count == 1
        assert (inbox / "book (1).pdf").exists()


class TestCLIHelp:
    def test_main_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "organize your books and PDFs" in result.output

    def test_ingest_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--confirm" in result.output

    def test_search_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "--author" in result.output

    def test_list_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--help"])
        assert result.exit_code == 0
        assert "--sort" in result.output

    def test_show_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["show", "--help"])
        assert result.exit_code == 0
        assert "IDENTIFIER" in result.output
