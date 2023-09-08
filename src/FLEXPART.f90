! SPDX-FileCopyrightText: FLEXPART 1998-2019, see flexpart_license.txt
! SPDX-License-Identifier: GPL-3.0-or-later

program flexpart

  !*****************************************************************************
  !                                                                            *
  !     This is the Lagrangian Particle Dispersion Model FLEXPART.             *
  !     The main program manages the reading of model run specifications, etc. *
  !     All actual computing is done within subroutine timemanager.            *
  !                                                                            *
  !     Author: A. Stohl                                                       *
  !                                                                            *
  !     18 May 1996                                                            *
  !                                                                            *
  !*****************************************************************************
  ! Changes:                                                                   *
  !   Unified ECMWF and GFS builds                                             *
  !   Marian Harustak, 12.5.2017                                               *
  !     - Added detection of metdata format using gributils routines           *
  !     - Distinguished calls to ecmwf/gfs gridcheck versions based on         *
  !       detected metdata format                                              *
  !     - Passed metdata format down to timemanager                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  !                                                                            *
  ! Constants:                                                                 *
  !                                                                            *
  !*****************************************************************************

  use point_mod
  use par_mod
  use com_mod
  use conv_mod
  use fdb_mod
  use timer_mod

  use random_mod, only: gasdev1
  use class_gribfile

  use fdb

#ifdef USE_NCF
  use netcdf_output_mod, only: writeheader_netcdf
#endif

  implicit none

  integer :: i, j, ix, jy, inest, iopt
  integer :: idummy = -320
  character(len=256) :: inline_options  !pathfile, flexversion, arg2
  integer :: metdata_format = GRIBFILE_CENTRE_UNKNOWN
  integer :: detectformat

  integer(kind=c_int) :: fdb_res

  timer_total  = new_timer("Total Flexpart Run")
  timer_readwind_loop  = new_timer("Readwind_ECMWF")
  timer_readwind_iter  = new_timer("Readwind Single Message")  
  timer_readwind_common  = new_timer("Readwind Message Decoding")  

  call start_timer(timer_total)

  ! Initialize fdb for data retreival
  !******************************************
  fdb_res = fdb_initialise()
  fdb_res = fdb_new_handle(fdb_handle)

  ! Generate a large number of random numbers
  !******************************************

  do i=1,maxrand-1,2
    call gasdev1(idummy,rannumb(i),rannumb(i+1))
  end do
  call gasdev1(idummy,rannumb(maxrand),rannumb(maxrand-1))


  ! FLEXPART version string
  flexversion_major = '10' ! Major version number, also used for species file names
  flexversion='Version '//trim(flexversion_major)//'.4.3 (2023-02-17)'
  verbosity=0

  ! Read the pathnames where input/output files are stored
  !*******************************************************

  inline_options='none'
  select case (command_argument_count())  ! Portable standard Fortran intrinsic procedure
  case (2)
    call get_command_argument(1,arg1)     ! Portable standard Fortran intrinsic procedure
    pathfile=arg1
    call get_command_argument(2,arg2)     ! Portable standard Fortran intrinsic procedure
    inline_options=arg2
  case (1)
    call get_command_argument(1,arg1)     ! Portable standard Fortran intrinsic procedure
    pathfile=arg1
    if (arg1(1:1).eq.'-') then
      write(pathfile,'(a11)') './pathnames'
      inline_options=arg1 
    endif
  case (0)
    write(pathfile,'(a11)') './pathnames'
  end select
  
  ! Print the GPL License statement
  !*******************************************************
  print*,'Welcome to FLEXPART ', trim(flexversion)
  print*,'FLEXPART is free software released under the GNU General Public License.'


  ! Ingest inline options
  !*******************************************************
  if (inline_options(1:1).eq.'-') then
    print*,'inline_options:',inline_options
    !verbose mode
    iopt=index(inline_options,'v') 
    if (iopt.gt.0) then
      verbosity=1
      !print*, iopt, inline_options(iopt+1:iopt+1)
      if  (trim(inline_options(iopt+1:iopt+1)).eq.'2') then
        print*, 'Verbose mode 2: display more detailed information during run'
        verbosity=2
      endif
    endif
    !debug mode 
    iopt=index(inline_options,'d')
    if (iopt.gt.0) then
      debug_mode=.true.
    endif
    if (trim(inline_options).eq.'-i') then
      print*, 'Info mode: provide detailed run specific information and stop'
      verbosity=1
      info_flag=1
    endif
    if (trim(inline_options).eq.'-i2') then
      print*, 'Info mode: provide more detailed run specific information and stop'
      verbosity=2
      info_flag=1
    endif
  endif
           
  if (verbosity.gt.0) then
    print*, 'nxmax=',nxmax
    print*, 'nymax=',nymax
    print*, 'nzmax=',nzmax
    print*,'nxshift=',nxshift 
  endif
  
  if (verbosity.gt.0) then
    write(*,*) 'call readpaths'
  endif 
  call readpaths
 
  if (verbosity.gt.1) then !show clock info 
     !print*,'length(4)',length(4)
     !count=0,count_rate=1000
     call system_clock(count_clock0, count_rate, count_max)
     !WRITE(*,*) 'SYSTEM_CLOCK',count, count_rate, count_max
     !WRITE(*,*) 'SYSTEM_CLOCK, count_clock0', count_clock0
     !WRITE(*,*) 'SYSTEM_CLOCK, count_rate', count_rate
     !WRITE(*,*) 'SYSTEM_CLOCK, count_max', count_max
  endif

  ! Read the user specifications for the current model run
  !*******************************************************

  if (verbosity.gt.0) then
    write(*,*) 'call readcommand'
  endif
  call readcommand
  if (verbosity.gt.0) then
    write(*,*) '    ldirect=', ldirect
    write(*,*) '    ibdate,ibtime=',ibdate,ibtime
    write(*,*) '    iedate,ietime=', iedate,ietime
    if (verbosity.gt.1) then   
      CALL SYSTEM_CLOCK(count_clock, count_rate, count_max)
      write(*,*) 'SYSTEM_CLOCK',(count_clock - count_clock0)/real(count_rate) !, count_rate, count_max
    endif
  endif

  if (fdbflag .eq. 1) then
    timer_readwind_fdb_inloop  = new_timer("Readwind Get Message Length (FDB)")
    timer_readwind_request  = new_timer("Readwind FDB Request")
    timer_fdb_datareader_read = new_timer("fdb_datareader_read_message")

    timer_fdb_request_datetime = new_timer("fdb_request_datetime")
    timer_fdb_create_request_dr = new_timer("fdb_create_request_dr")
    timer_fdb_datareader_open = new_timer("fdb_datareader_open")
    timer_fdb_get_max_message_len = new_timer("fdb_get_max_message_len")
    timer_allocate_buf = new_timer("allocate_buf")
    timer_fdb_datareader_tell = new_timer("fdb_datareader_tell")

    timer_fdb_setup_request = new_timer("fdb_setup_request")
    timer_fdb_new_dr = new_timer("fdb_new_datareader")
    timer_fdb_retrieve = new_timer("fdb_retrieve")

    timer_fdb_inspect = new_timer("fdb_inspect")
  endif

  ! Initialize arrays in com_mod
  !*****************************
  call com_mod_allocate_part(maxpart)


  ! Read the age classes to be used
  !********************************
  if (verbosity.gt.0) then
    write(*,*) 'call readageclasses'
  endif
  call readageclasses

  if (verbosity.gt.1) then   
    CALL SYSTEM_CLOCK(count_clock, count_rate, count_max)
    write(*,*) 'SYSTEM_CLOCK',(count_clock - count_clock0)/real(count_rate) !, count_rate, count_max
  endif     

  ! Read, which wind fields are available as files OR 
  ! Identify which fields should be fetched from fdb 
  ! within the modelling period
  !***************************************************
  
  if (fdbflag.eq.0) then
    if (verbosity.gt.0) then
      write(*,*) 'call readavailable'
    endif
  endif
  if (fdbflag.eq.0) then
    call readavailable
  else
    call get_fdbtimes
  end if

  ! Detect metdata format
  !**********************
  if (verbosity.gt.0) then
    write(*,*) 'call detectformat'
  endif

  metdata_format = detectformat()

  if (metdata_format.eq.GRIBFILE_CENTRE_ECMWF) then
    print *,'ECMWF metdata detected'
  elseif (metdata_format.eq.GRIBFILE_CENTRE_NCEP) then
    print *,'NCEP metdata detected'
  else
    print *,'Unknown metdata format'
    stop
  endif



  ! If nested wind fields are used, allocate arrays
  !************************************************

  if (verbosity.gt.0) then
    write(*,*) 'call com_mod_allocate_nests'
  endif
  call com_mod_allocate_nests

  ! Read the model grid specifications,
  ! both for the mother domain and eventual nests
  !**********************************************

  if (verbosity.gt.0) then
    write(*,*) 'call gridcheck'
  endif

  if (metdata_format.eq.GRIBFILE_CENTRE_ECMWF) then
    call gridcheck_ecmwf
  else
    call gridcheck_gfs
  end if

  if (verbosity.gt.1) then   
    CALL SYSTEM_CLOCK(count_clock, count_rate, count_max)
    write(*,*) 'SYSTEM_CLOCK',(count_clock - count_clock0)/real(count_rate) !, count_rate, count_max
  endif      

  if (verbosity.gt.0) then
    write(*,*) 'call gridcheck_nests'
  endif  
  call gridcheck_nests

  ! Read the output grid specifications
  !************************************

  if (verbosity.gt.0) then
    write(*,*) 'call readoutgrid'
  endif

  call readoutgrid

  if (nested_output.eq.1) then
    call readoutgrid_nest
    if (verbosity.gt.0) then
      write(*,*) '# readoutgrid_nest'
    endif
  endif

  ! Read the receptor points for which extra concentrations are to be calculated
  !*****************************************************************************

  if (verbosity.eq.1) then
    print*,'call readreceptors'
  endif
  call readreceptors

  ! Read the physico-chemical species property table
  !*************************************************
  !SEC: now only needed SPECIES are read in readreleases.f
  !call readspecies

  ! Read the landuse inventory
  !***************************

  if (verbosity.gt.0) then
    print*,'call readlanduse'
  endif
  call readlanduse

  ! Assign fractional cover of landuse classes to each ECMWF grid point
  !********************************************************************

  if (verbosity.gt.0) then
    print*,'call assignland'
  endif
  call assignland

  ! Read the coordinates of the release locations
  !**********************************************

  if (verbosity.gt.0) then
    print*,'call readreleases'
  endif
  call readreleases

  ! Read and compute surface resistances to dry deposition of gases
  !****************************************************************

  if (verbosity.gt.0) then
    print*,'call readdepo'
  endif
  call readdepo

  ! Convert the release point coordinates from geografical to grid coordinates
  !***************************************************************************

  call coordtrafo  
  if (verbosity.gt.0) then
    print*,'call coordtrafo'
  endif

  ! Initialize all particles to non-existent
  !*****************************************

  if (verbosity.gt.0) then
    print*,'Initialize all particles to non-existent'
  endif
  do j=1,maxpart
    itra1(j)=-999999999
  end do

  ! For continuation of previous run, read in particle positions
  !*************************************************************

  if (ipin.eq.1) then
    if (verbosity.gt.0) then
      print*,'call readpartpositions'
    endif
    call readpartpositions
  else
    if (verbosity.gt.0) then
      print*,'numpart=0, numparticlecount=0'
    endif
    numpart=0
    numparticlecount=0
  endif

  ! Calculate volume, surface area, etc., of all output grid cells
  ! Allocate fluxes and OHfield if necessary
  !***************************************************************

  if (verbosity.gt.0) then
    print*,'call outgrid_init'
  endif
  call outgrid_init
  if (nested_output.eq.1) call outgrid_init_nest

  ! Read the OH field
  !******************

  if (OHREA.eqv..TRUE.) then
    if (verbosity.gt.0) then
      print*,'call readOHfield'
    endif
    call readOHfield
  endif

  ! Write basic information on the simulation to a file "header"
  ! and open files that are to be kept open throughout the simulation
  !******************************************************************

#ifdef USE_NCF
  if (lnetcdfout.eq.1) then 
    call writeheader_netcdf(lnest=.false.)
  else 
    call writeheader
  end if

  if (nested_output.eq.1) then
    if (lnetcdfout.eq.1) then
      call writeheader_netcdf(lnest=.true.)
    else
      call writeheader_nest
    endif
  endif
#endif

  if (verbosity.gt.0) then
    print*,'call writeheader'
  endif

  call writeheader
  ! FLEXPART 9.2 ticket ?? write header in ASCII format 
  call writeheader_txt
  !if (nested_output.eq.1) call writeheader_nest
  if (nested_output.eq.1.and.surf_only.ne.1) call writeheader_nest
  if (nested_output.eq.1.and.surf_only.eq.1) call writeheader_nest_surf
  if (nested_output.ne.1.and.surf_only.eq.1) call writeheader_surf

  !open(unitdates,file=path(2)(1:length(2))//'dates')

  if (verbosity.gt.0) then
    print*,'call openreceptors'
  endif
  call openreceptors
  if ((iout.eq.4).or.(iout.eq.5)) call openouttraj

  ! Releases can only start and end at discrete times (multiples of lsynctime)
  !***************************************************************************

  if (verbosity.gt.0) then
    print*,'discretize release times'
  endif
  do i=1,numpoint
    ireleasestart(i)=nint(real(ireleasestart(i))/real(lsynctime))*lsynctime
    ireleaseend(i)=nint(real(ireleaseend(i))/real(lsynctime))*lsynctime
  end do

  ! Initialize cloud-base mass fluxes for the convection scheme
  !************************************************************

  if (verbosity.gt.0) then
    print*,'Initialize cloud-base mass fluxes for the convection scheme'
  endif

  do jy=0,nymin1
    do ix=0,nxmin1
      cbaseflux(ix,jy)=0.
    end do
  end do
  do inest=1,numbnests
    do jy=0,nyn(inest)-1
      do ix=0,nxn(inest)-1
        cbasefluxn(ix,jy,inest)=0.
      end do
    end do
  end do

  ! Inform whether output kernel is used or not
  !*********************************************
  if (lroot) then
    if (.not.lusekerneloutput) then
      write(*,*) "Concentrations are calculated without using kernel"
    else
      write(*,*) "Concentrations are calculated using kernel"
    end if
  end if


  ! Calculate particle trajectories
  !********************************

  if (verbosity.gt.0) then
     if (verbosity.gt.1) then   
       CALL SYSTEM_CLOCK(count_clock, count_rate, count_max)
       write(*,*) 'SYSTEM_CLOCK',(count_clock - count_clock0)/real(count_rate) !, count_rate, count_max
     endif
     if (info_flag.eq.1) then
       print*, 'info only mode (stop)'    
       stop
     endif
     print*,'call timemanager'
  endif

  if (verbosity.gt.0) write (*,*) 'timemanager> call wetdepo'
  call timemanager(metdata_format)
 

  if (verbosity.gt.0) then
! NIK 16.02.2005 
    do i=1,nspec
      if (tot_inc_count(i).gt.0) then
         write(*,*) '**********************************************'
         write(*,*) 'Scavenging statistics for species ', species(i), ':'
         write(*,*) 'Total number of occurences of below-cloud scavenging', &
           & tot_blc_count(i)
         write(*,*) 'Total number of occurences of in-cloud    scavenging', &
           & tot_inc_count(i)
         write(*,*) '**********************************************'
      endif
    end do
  endif
  
  write(*,*) 'CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLE&
       &XPART MODEL RUN!'

  call stop_timer(timer_total)

  call print_timers()

end program flexpart
