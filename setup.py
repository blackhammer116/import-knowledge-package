from setuptools import setup, find_packages

setup(
    name="import-knowledge-package",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A package for importing knowledge and embedding text.",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/import-knowledge-package",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "chromadb",
        "openai",
        "python-dotenv",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)