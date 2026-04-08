class Wst < Formula
  include Language::Python::Virtualenv

  desc "CLI tool for organizing books and PDFs with AI-powered metadata"
  homepage "https://github.com/cnexans/wst"
  url "https://pypi.org/packages/source/w/wst-library/wst_library-0.1.0.tar.gz"
  # sha256 "UPDATE_WITH_ACTUAL_SHA256_AFTER_PYPI_PUBLISH"
  license "MIT"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "organize your books", shell_output("#{bin}/wst --help")
  end
end
