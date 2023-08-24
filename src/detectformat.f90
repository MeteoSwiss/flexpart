! SPDX-FileCopyrightText: FLEXPART 1998-2019, see flexpart_license.txt
! SPDX-License-Identifier: GPL-3.0-or-later

integer function detectformat()

  !*****************************************************************************
  !                                                                            *
  !   This routine reads the 1st file with windfields to determine             *
  !   the format.                                                              *
  !                                                                            *
  !     Authors: M. Harustak                                                   *
  !                                                                            *
  !     6 May 2015                                                             *
  !                                                                            *
  !   Unified ECMWF and GFS builds                                             *
  !   Marian Harustak, 12.5.2017                                               *
  !     - Added routine to FP10 Flexpart distribution                          *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! fname                file name of file to check                            *
  !                                                                            *
  !*****************************************************************************

  use par_mod
  use com_mod
  use class_gribfile
  use fdb_mod


  implicit none

  character(len=255) :: filename
  character(len=255) :: wfname1(maxwf)
  integer :: metdata_format

  ! If no file is available
  if ( maxwf.le.0 ) then
    print*,'No wind file available'
    detectformat = GRIBFILE_CENTRE_UNKNOWN
    return
  endif

  if (fdbflag.eq.0) then
    ! construct filename and get format
    filename = path(3)(1:length(3)) // trim(wfname(1))
    detectformat = gribfile_centre(TRIM(filename))
  else
    detectformat = fdb_grib_centre(1)
  end if

end 
