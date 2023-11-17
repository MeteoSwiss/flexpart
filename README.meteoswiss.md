FLEXPART for MeteoSwiss
=======================

FLEXPART for IFS (and GFS) adapted source code
for operational MeteoSwiss production.


Installation
------------

### Using the `spack` package

This requires at lease spack-c2sm v0.20.1.2.
Activate [spack-c2sm](https://github.com/C2SM/spack-c2sm/blob/main/README.md)
and build flexpart with `spack`: 

    spack dev-build -u build flexpart-ifs @develop %gcc

### Using `make` (without `spack`)

Change to the `scr` directory 
and load the appropriate modules for the GCC programming environment:

    cd src
    . CSCS.env

Use `make` with the makefile `makefile_meteoswiss` to build the application. 

    make -f makefile_meteoswiss

For compilation of serial FLEXPART (see header of makefile)

    make -f makefile_meteoswiss serial

For compilation of serial FLEXPART for debugging (see header of makefile)

    make -f makefile_meteoswiss serial-dbg

For compilation of parallel FLEXPART (see header of makefile)

    make -f makefile_meteoswiss mpi

For compilation of parallel FLEXPART for debugging (see header of makefile)

    make -f makefile_meteoswiss mpi-dbg
    
To clean the object, module and executable files

    make -f makefile_meteoswiss clean


Test FLEXPART
-------------

See the [README.md](test_meteoswiss/README.md) file in the `test_meteoswiss` directory 
for testing instructions.


Run FLEXPART
------------

To run flexpart, it may be necessary to unlimit the stacksize:

    ulimit -s unlimited

To run without spack, load modules as provided in CSCS.env

    . CSCS.env

Run flexpart with

    ./FLEXPART
or

    ./FLEXPART_MPI
