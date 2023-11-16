# README #

This repository contains the Lagrangian particle dispersion model FLEXPART.

### Dependencies

 * Jasper and grib_api or ECCodes
 * NetCDF (optional)

### Compilation

To compile for MeteoSwiss read [README.meteoswiss.md](README.meteoswiss.md).

Otherwise edit the `makefile` to adapt the paths to the libraries and the include files, then:

```
> cd src
> make 
```

### Deployment instructions 

FLEXPART is a standalone executable. Run it with

    ./src/FLEXPART
    
in the main directory.

For more information about FLEXPART version 10, see [www.flexpart.eu](https://www.flexpart.eu)
