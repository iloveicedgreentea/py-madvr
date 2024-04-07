import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="py_madvr2",
    version="1.5.4",
    author="iloveicedgreentea2",
    description="A package to control MadVR Envy over IP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/iloveicedgreentea/py-madvr",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
