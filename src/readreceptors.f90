! SPDX-FileCopyrightText: FLEXPART 1998-2019, see flexpart_license.txt
! SPDX-License-Identifier: GPL-3.0-or-later

subroutine readreceptors

  !*****************************************************************************
  !                                                                            *
  !     This routine reads the user specifications for the receptor points.    *
  !                                                                            *
  !     Author: A. Stohl                                                       *
  !     1 August 1996                                                          *
  !     HSO, 14 August 2013: Added optional namelist input                     *
  !     PS, 2020-05-28: correct bug in nml input, code cosmetics               *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! receptorarea(maxreceptor)  area of dx*dy at location of receptor           *
  ! receptorname(maxreceptor)  names of receptors                              *
  ! xreceptor,yreceptor  coordinates of receptor points                        *
  !                                                                            *
  ! Constants:                                                                 *
  ! unitreceptor         unit connected to file RECEPTORS                      *
  !                                                                            *
  !*****************************************************************************

  use par_mod
  use com_mod

  implicit none

  integer :: j
  real :: x,y,xm,ym
  character(len=16) :: receptor

  integer :: ierr
  real :: lon,lat   ! for namelist input, lon/lat are used instead of x,y
  integer,parameter :: iunitreceptorout=2

  ! declare namelist
  namelist /receptors/ receptor, lon, lat

  ! For backward runs, do not allow receptor output. Thus, set number of receptors to zero
  !*****************************************************************************

  if (ldirect.lt.0) then
    numreceptor=0
    return
  endif

! prepare namelist output if requested
  if (nmlout .and. lroot) &
    open(iunitreceptorout,file=path(2)(1:length(2))//'RECEPTORS.namelist', &
      status='replace',err=1000)

! Open the RECEPTORS file and read output grid specifications
!************************************************************
! try namelist input
  open(unitreceptor,file=path(1)(1:length(1))//'RECEPTORS',status='old',err=999)
  read(unitreceptor,receptors,iostat=ierr)
  close(unitreceptor)

  open(unitreceptor,file=path(1)(1:length(1))//'RECEPTORS')

  if (ierr.ne.0) then ! not namelist
  
    call skplin(5,unitreceptor)

    ! Read the names and coordinates of the receptors
    !************************************************

    j=0
100 j=j+1
      read(unitreceptor,*,end=99)
      read(unitreceptor,*,end=99)
      read(unitreceptor,*,end=99)
      read(unitreceptor,'(4x,a16)',end=99) receptor
      call skplin(3,unitreceptor)
      read(unitreceptor,'(4x,f11.4)',end=99) x
      call skplin(3,unitreceptor)
      read(unitreceptor,'(4x,f11.4)',end=99) y
      if (x.eq.0. .and. y.eq.0. .and. receptor.eq.'                ') then
        j=j-1
        goto 100
      endif
      if (j.gt.maxreceptor) goto 998 ! ERROR - STOP
      receptorname(j)=receptor
      xreceptor(j)=(x-xlon0)/dx       ! transform to grid coordinates
      yreceptor(j)=(y-ylat0)/dy
      xm=r_earth*cos(y*pi/180.)*dx/180.*pi
      ym=r_earth*dy/180.*pi
      receptorarea(j)=xm*ym

      ! write receptors file in namelist format to output directory if requested
      if (nmlout .and. lroot) then
        lon=x
        lat=y
        write(iunitreceptorout,nml=receptors)
      endif

    goto 100 ! read next

99  numreceptor=j-1 ! read all

  else ! continue with namelist input

    j=0
    do while (ierr.eq.0)
      j=j+1
      read(unitreceptor,receptors,iostat=ierr)
      if (ierr.eq.0) then
        if (j.gt.maxreceptor) goto 998 ! ERROR - STOP
        receptorname(j)=receptor
        xreceptor(j)=(lon-xlon0)/dx       ! transform to grid coordinates
        yreceptor(j)=(lat-ylat0)/dy
        xm=r_earth*cos(lat*pi/180.)*dx/180.*pi
        ym=r_earth*dy/180.*pi
        receptorarea(j)=xm*ym
      ! write receptors file in namelist format to output directory if requested
        if (nmlout.and.lroot) &
        write(iunitreceptorout,nml=receptors)
      endif
    end do
    numreceptor=j-1
    close(unitreceptor)

  endif ! end reading nml input

  if (nmlout.and.lroot) &
    close(iunitreceptorout)

  return

998 continue
  write(*,*) ' #### FLEXPART MODEL ERROR! TOO MANY RECEPTOR #### '
  write(*,*) ' #### POINTS ARE GIVEN.                       #### '
  write(*,*) ' #### MAXIMUM NUMBER IS ',maxreceptor,'       #### '
  write(*,*) ' #### PLEASE MAKE CHANGES IN FILE RECEPTORS   #### '
  stop 1

999 continue
  write(*,*) ' #### FLEXPART MODEL ERROR! FILE "RECEPTORS"  #### '
  write(*,*) ' #### CANNOT BE OPENED IN THE DIRECTORY       #### '
  write(*,'(a)') path(1)(1:length(1))
  stop 1

1000 continue
  write(*,*) ' #### FLEXPART MODEL ERROR! FILE "RECEPTORS"  #### '
  write(*,*) ' #### CANNOT BE OPENED IN THE DIRECTORY       #### '
  write(*,'(a)') path(2)(1:length(2))
  stop 1

end subroutine readreceptors
