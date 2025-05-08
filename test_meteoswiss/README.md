Calculate a dispersion simulation and plot results
==================================================

Testing with script `test-fp`
-----------------------------

Test script to prepare input data and run Flexpart. It
- Retrieves GRIB file from the operational or from a personal ICON storage
- Generates the `pathnames` and the `AVAILABLE` files
- Adapts the FLEXPART control input files according to the provided arguments
- Writes a batch-job file
- Submits the job on a queue

See usage and a short help with command

    ./test-fp --help

For all settings see the settings section of the script.

When the script is called with no options or not all of the mandatory input,
it will prompt the user to select from command-line menus.

    ./test-fp


The batch job and its input and output are written to the directory
`$SCRATCH/flexpart/job/<job-tag>`

The job tag <job-tag> is an automatically increased number by default, but can be
set manually with the `-j/--job` option. The last automatically generated number is stored in
`$HOME/.flexpart_job`, never modify this file manually unless you know what you are doing!


Plotting with Python application `pyflexplot`
---------------------------------------------

The `pyflexplot` application creates plots from FLEXPART NetCDF output (generated with option `IOUT=9`).

The shell-script `plot_output` may be used to set up the pyflexplot command for the
operational plots for the NAZ and submit it as batch job. It uses the directory
structure set up by `test-fp` and the therein stored files `test-fp.log` and
`output/plot_info`. It takes the job number or name as an optional argument. If no argument is given, it looks for the newest job number registered in file `$HOME/.flexpart_job`.

    ./plot_output [job-tag]

To instead use `pyflexplot` manually, follow the procedure in the secton below.

Manual plotting with `pyflexplot`
---------------------------------

Initialize the operational environment:

    source /oprusers/osm/.opr_setup_dir

Standard set of plots are produced with one of the following presets.
Obtain the current set of available presets with:

    pyflexplot --preset=?

Current operational presets:

    opr/cosmo-1e/all_???
    opr/cosmo-1e-ctrl/all_???
    opr/ifs-hres-eu/all_???
    opr/ifs-hres/all_???

Usage of `pyflexplot`:
```
pyflexplot --preset <preset> --merge-pdfs \
           --setup infile grid_conc_<YYYYMMDDhhmmss>.nc \
           --setup base_time <YYYYMMDDhh>
```
where `<preset>` is the appropriate preset from the list above,
      `<YYYYMMDDhhmmss>` is the reference time of the FLEXPART run, and
      `<YYYYMMDDhh>` is the base time of the model run used.

The plotting can be accelerated by first allocating a slurm partition with
several parallel processes and run `pyflexplot` in parallel.

### Example

Run pyflexplot with 10 parallel processes for Flexpart output produced with
COSMO-1E-Control:
```
salloc --cpus-per-task=10
pyflexplot --preset=opr/cosmo-1e-ctrl/all_pdf --merge-pdfs \
	   --setup infile *.nc \
	   --num-procs=$SLURM_CPUS_PER_TASK
exit
```

Debug with data from a COSMO Package run
----------------------------------------

Locate the temporary working directory of the COSMO Package and copy the directory to a more
persistent location like `$SCRATCH`.

Location of the operational runs of the operational user osm:

    /opr/osm/tmp/<date>_<version>/lm_flexpart_c_wd_<job-no>/01

Change to the copied directory. Adapt the `pathnames` file to the new
location. Continue with the third paragraph of the next section.


Interactive runs
----------------

For debugging or performance testing, it might be useful to run
FLEXPART interactively. You may run `test-fp` with the option `-n` to see
the commands needed to prepare a FLEXPART run, or use the option `-s` to
actually execute the preparational commands but stop just before
submission of the batch job running FLEXPART.

Look into the job file to see the commands needed. They depend on
whether the code is compiled as serial or as parallel code.

Load the necessary modules to run FLEXPART:

    source FLEXPART.env

Allocate parallel processes and run FLEXPART in the job directory
with:
```
salloc -n 10  # allocate 10 parallel processes (COSMO version only)
export OMP_NUM_THREADS=10  # OMP to create 10 threads (COSMO version only)
ulimit -s unlimited  # FLEXPART needs unlimited stacksize
./FLEXPART
exit  # free allocation
```
