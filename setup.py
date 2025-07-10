# -*- coding: utf-8 -*-
"""README同步管理器 - 安装配置"""

from setuptools import setup, find_packages

# 读取README文件
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# 读取requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="readme-sync-manager",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="扁平化管理所有项目的README.md文件，支持双向同步",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/readme-sync-manager",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Filesystems",
        "Topic :: Utilities",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "readme-sync=readme_sync.cli:cli",
        ],
    },
    include_package_data=True,
    keywords="readme sync markdown documentation files management",
    zip_safe=False,
)
