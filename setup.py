# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
import re
import ast

_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('requirements.txt') as f:
    install_requires = f.read().strip().split('\n')

with open('frappe_gcp_attachment/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))

setup(
    name='frappe_gcp_attachment',
    version=version,
    description='Frappe app to upload file attachments to Google Cloud Storage.',
    author='Nirmaan',
    author_email='techadmin@nirmaan.app',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    dependency_links=[]
)
