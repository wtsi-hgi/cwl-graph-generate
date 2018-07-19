from setuptools import setup, find_packages
import sys
if sys.version_info < (3, 6):
    sys.exit('Sorry, Python < 3.6 is not supported')

try:
    from pypandoc import convert

    def read_markdown(file):
        return convert(file, "rst")
except ImportError:
    def read_markdown(file):
        return open(file, "r").read()

setup(
    name="cwl-graph-generate",
    python_requires='>=3.6, <4',
    version="0.1",
    packages=find_packages(exclude=["tests"]),
    install_requires=open("requirements.txt", "r").readlines(),
    url="https://github.com/wtsi-hgi/unjsify_cwl",
    package_data={'': ['*.js', "VERSION"]},
    include_package_data=True,
    license="MIT",
    description="TODO",
    long_description=read_markdown("README.md"),
    entry_points={
        "console_scripts": [
            "cwl-graph-generate=cwl_graph_generate:main",
        ]
    }
)