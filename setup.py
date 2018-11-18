import sys

from setuptools import find_packages, setup

REQUIRES = [
    'Flask>=0.8'
    'jinja2>=2.6',
    'sutekh>=0.9.4',
]

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name="Sutekh-Web",
    version="0.2.0",
    url='https://github.com/drnlm/Sutekh-Web',
    license='GPL',
    description="A simple web interface to the Sutekh VTES card database",
    long_description=long_description,
    author='Neil Muller',
    author_email='drnlmuller+sutekh@gmail.com',
    packages=find_packages(),
    include_package_data=True,
    install_requires=REQUIRES,
    dependency_links=SOURCES,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Framework :: Flask',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Internet :: WWW/HTTP',
    ],
)
