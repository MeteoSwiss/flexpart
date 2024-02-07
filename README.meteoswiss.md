FLEXPART for IFS and GFS
========================

Installation at CSCS for MeteoSwiss
-----------------------------------

Note: These are the instructions to install
FLEXPART for IFS and GFS 
at the CSCS for MeteoSwiss. 
For all other installations, see the [README.md](README.md) file.

### Using the `spack` package

This requires at least spack-c2sm v0.20.1.2.
Activate [spack-c2sm](https://github.com/C2SM/spack-c2sm/blob/main/README.md)
and build flexpart with `spack`: 

    spack dev-build -u build flexpart-ifs @main

### Using `make` (without `spack`)

`makefile_meteoswiss` requires four environment variables:
- ECCODES_DIR: The directory where eccodes is installed.
- ECCODES_LD_FLAGS: The ld flags of eccodes.
- NETCDF_FORTRAN_INCLUDE: The include flag to include netcdf.
- NETCDF_FORTRAN_LD_FLAGS The ld flags of netcdf.

They are curated by `CSCS.env` for CSCS machines through module interfaces.

Change to the `scr` directory 
and load the appropriate modules for the GCC programming environment:

    cd src
    . CSCS.env

Use `make` with the makefile `makefile_meteoswiss` to build the executable.
The `serial` target is the default:

    make -f makefile_meteoswiss

This builds a serial version of FLEXPART (see header of makefile) and is the same as:

    make -f makefile_meteoswiss serial

To build a serial FLEXPART for debugging:

    make -f makefile_meteoswiss serial-dbg

To build a  parallel FLEXPART:

    make -f makefile_meteoswiss mpi

To build a  parallel FLEXPART for debugging:

    make -f makefile_meteoswiss mpi-dbg
    
To clean up all object, module, and executable files

    make -f makefile_meteoswiss clean


Test FLEXPART
-------------

See the [README.md](test_meteoswiss/README.md) file in the `test_meteoswiss` directory 
for testing instructions.


Run FLEXPART
------------

To run flexpart, it may be necessary to unlimit the stacksize:

    ulimit -s unlimited

To run without spack, load modules as provided in `CSCS.env`.

    . CSCS.env

Run flexpart with

    ./FLEXPART

or

    ./FLEXPART_MPI
