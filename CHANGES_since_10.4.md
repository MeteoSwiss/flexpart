Code changes since 10.4
=======================

Bugfixes and enhancements in this repository since official release 10.4

Bugfixes
--------

* options/SPECIES/SPECIES_009: corrected wrong number format, replaced comma by
  decimal point
* options/SPECIES/SPECIES_028: corrected wrong number format, moved sign of
  exponent to after the E
* options/SPECIES/specoverview.f90: added namelist parameters that appear in
  SPECIES files but were missing in this program, causing read errors.
* src/advance.f90: resolution-independent calculation of the new longitude if
  a particle crosses either pole (i.e. if a particle is advected to below -90 or
  above 90 degree latitude, the calculation of the new longitude was hardcoded for
  1 degree resolution). Do not put the particle back into the domain at all if 
  it crosses the lower or upper boundary in a limited area simulation.
* src/caldate.f90: avoid to output hour 240000, change made by Petra for her
  version 10.4.1
* src/FLEXPART.f90: replaced compiler-specific command line argument routines
  by standard Fortran intrinsic routines
* src/FLEXPART_MPI.f90: ditto
* src/gridcheck_ecmwf.f90: corrected handling of vertical levels when input
  file do not contain uppermost layers (changes suggested by Stephan Henne).
* src/gridcheck_nests.f90: ditto
* src/makefile: NetCDF output as default option, hint about compiler troubles
  (relocation error, use -mcmodel=large) caused by -O0, and other changes by
  Petra for version 10.4.1
* src/readwind_ecmwf.f90: corrected handling of vertical levels when input file
  do not contain uppermost layers and corrected conversion_factor for convective
  precipitation and snow height in GRIB2
* src/readwind_ecmwf_mpi.f90: ditto
* src/readwind_nests.f90: ditto
* src/timemanager.f90: removed non-standard-conformant argument aliasing and
  corrected kind type declaration causing troubles with some compilers
* src/verttransform.f90: removed superfluous comma (change made independently by
  both myself and Petra for version 10.4.1)
* src/readwind_ecmwf_mpi.f90: ditto
 
Code enhancements
-----------------
* options/OUTGRID: added comments describing contents
* options/SPECIES/SPECIES_*: aligned comments 
* options/SPECIES/specoverview.f90: removed commented lines, rectified lines
  indenting
* src/FLEXPART.f90: rectified lines indenting, updated version (to 10.4.3) and date
  in version string
* src/FLEXPART_MPI.f90: ditto, and realigned code with src/FLEXPART.f90
* src/gridcheck_*.f90: added code to write out name of file before it is opened
  (helps a lot for debugging when an input file causes troubles)
* src/par_mod.f90: added comment explaining relevance of nuvzmax for GRIB input
* src/readreceptors.f90: Code cosmetics by Petra for version 10.4.1
* src/readreleases.f90: write out warning if too few particles are used to
  randomize release
* src/readspecies.f90: write out name of SPECIES file before it is read
* src/readwind_*.f90: write out name of input file before opening it
* src/verttransform_ecmwf.f90: Code enhancements made by Petra for version 10.4.1
* src/writeheader_txt.f90: removed wrong comment
