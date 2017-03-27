"""
    setup.py - Setup file to distribute the library

See Also:
    https://github.com/pypa/sampleproject
    https://packaging.python.org/en/latest/distributing.html
    https://pythonhosted.org/an_example_pypi_project/setuptools.html
"""
import os
import sys
import argparse
import glob

from setuptools import setup, find_packages

import uuid
from pip.req import parse_requirements


COMMON_TEXT_EXTENSIONS = ['.txt', '', '.rst', '.md']

def find_file(filename, extensions=COMMON_TEXT_EXTENSIONS):
    """Search through common file extensions for the given filename and return the filename with 
    the extension if it is found.

    Args:
        filename (str): Base filename that you don't know the extension for.
        extensions (list) [COMMON_TEXT_EXTENSIONS]: A list (of str) file extensions to search for.

    Raises:
        FileNotFoundError if the file does not exist for any of the extensions.

    Returns:
        filename (str): Filename that exists with the first found extension
    """
    filename, ext = os.path.splitext(filename)
    if ext != "" and ext not in extensions:
        extensions = [ext] + extensions # copy
    for ext in extensions:
        test_filename = filename + ext
        if os.path.exists(test_filename):
            return test_filename

    raise FileNotFoundError
# end find_file

def get_readme_text(path=".", name="README"):
    """Return the text inside of the README file.
    
    Args:
        path (str)["."]: Path to look for the file
        name (str): Base README filename (Will automatically look for the extension based on common file extensions).
    
    Returns:
        long_description (str): Text read from the README file. "" if the README file was not found.
    """
    # Readme
    try:
        readme = find_file(os.path.join(path, name))
        with open(readme, "rb") as file:
            long_description = file.read().decode('utf-8', 'replace')
        return long_description
    except FileNotFoundError:
        return ""
# end get_readme_text


def get_packages(path="."):
    """Return all of the python packages (library folder with __init__.py) that are in the path.""" 
    return find_packages(where=path, exclude=["build/*", "dist/*"])
# end get_packages


def get_requirements(path=".", name="requirements"):
    """Return a list of requirements for the library from a requirements file.

    Args:
        path (str)["."]: Path to look for the file
        name (str): Base requirements filename (Will automatically look for the extension based on common file extensions).
    
    Returns:
        requirements (list): List of required library names.
    """
    try:
        requirements_file = find_file(os.path.join(path, name))
        requirements = [str(ir.req)
                        for ir in parse_requirements(requirements_file, session=uuid.uuid1())
                                if ir.req is not None]
        return requirements
    except FileNotFoundError:
        return []
# end get_requirements

setup(
    name="pyiridium9602",
    version="0.1",
    description="Python 3 iridium communication library for the iridium 9602 modem.",
    url="https://github.com/HashSplat/pyiridium9602",

    author="SeaLandAire Technologies Inc.",
    author_email="jengel@sealandaire.com",
    
    license="MIT",

    platforms="any",
    classifiers=["Programming Language :: Python",
                 "Programming Language :: Python :: 3",
                 "Operating System :: OS Independent",],

    scripts=[file for file in glob.glob("bin/*.py")],

    long_description=get_readme_text(),
    packages=get_packages(),
    install_requires=get_requirements(),
    
    include_package_data=True,
    #package_data={
    #    'package': ['file.dat']
    #}
    
    # options to install extra requirements
    # extras_require={ 
    #     'dev': [],
    #     'test': ['converage'],
    # }
    
    # Data files outside of packages
    # data_files=[('my_data', ['data/data_file'])],
    
    # keywords='sample setuptools development'
    
    # entry_points={
    #     'console_scripts': [
    #         'foo = my_package.some_module:main_func',
    #         'bar = other_module:some_func',
    #     ],
    #     'gui_scripts': [
    #         'baz = my_package_gui:start_func',
    #     ]
    # }
)
