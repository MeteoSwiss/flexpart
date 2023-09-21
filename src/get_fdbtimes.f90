! SPDX-FileCopyrightText: FLEXPART 1998-2019, see flexpart_license.txt
! SPDX-License-Identifier: GPL-3.0-or-later

subroutine get_fdbtimes

  !*****************************************************************************
  !                                                                            *
  !   This routine reads the dates and times for which windfields are          *
  !   available.                                                               *
  !                                                                            * 
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! bdate                beginning date as Julian date                         *
  ! beg                  beginning date for windfields                         *
  ! end                  ending date for windfields                            *
  ! ideltas [s]          duration of modelling period                          *
  ! idiff                time difference between 2 wind fields                 *
  ! idiffnorm            normal time difference between 2 wind fields          *
  ! idiffmax [s]         maximum allowable time between 2 wind fields          *
  ! jul                  julian date, help variable                            *
  ! numbwf               actual number of wind fields                          *
  ! wftime(maxwf) [s]times of wind fields relative to beginning time           *
  ! wftime1 = same as above, but only local (help variables)   *
  !                                                                            *
  ! Constants:                                                                 *
  ! maxwf                maximum number of wind fields                         *
  ! unitavailab          unit connected to file AVAILABLE                      *
  !                                                                            *
  !*****************************************************************************

  use par_mod
  use com_mod

  implicit none

  integer :: i,idiff,ldat,ltim,wftime1(maxwf),numbwfn(maxnests),k
  integer :: wfforecasttime1(maxwf), wfstep1(maxwf), wfdate1(maxwf)
  integer :: wftime1n(maxnests,maxwf),wftimen(maxnests,maxwf)
  logical :: lwarntd=.true.
  logical :: debugfdb=.false.
  real(kind=dp) :: juldate,jul,beg,end

  character(len=12) :: wfdatetime1(maxwf)
  character(len=6) :: ibtime_str
  integer :: ibtime_H

  ! Windfields are only used, if they are within the modelling period.
  ! However, 1 additional day at the beginning and at the end is used for
  ! interpolation. -> Compute beginning and ending date for the windfields.
  !************************************************************************

  if (ideltas.gt.0) then         ! forward trajectories
    beg=bdate-1._dp
    end=bdate+real(ideltas,kind=dp)/86400._dp+real(idiffmax,kind=dp)/ &
          86400._dp
  else                           ! backward trajectories
    beg=bdate+real(ideltas,kind=dp)/86400._dp-real(idiffmax,kind=dp)/ &
          86400._dp
    end=bdate+1._dp
  endif

  if (debugfdb) WRITE(*,*) 'bdate:' , bdate
  if (debugfdb) WRITE(*,*) 'beg:' , beg
  if (debugfdb) WRITE(*,*) 'end:' , end
  if (debugfdb) WRITE(*,*) 'ideltas:' , ideltas
  if (debugfdb) WRITE(*,*) 'idiffmax:' , idiffmax
  if (debugfdb) WRITE(*,*) 'maxwf:' , maxwf
  if (debugfdb) write(*,*) 'ibdate,ibtime=',ibdate,ibtime
  if (debugfdb) write(*,*) 'iedate,ietime=', iedate,ietime


  write(ibtime_str, '(I6.6)')  ibtime
  if (debugfdb) WRITE(*,*) 'ibtime_str:' , ibtime_str
  read(ibtime_str(1:2), '(I2)')  ibtime_H
  if (debugfdb) WRITE(*,*) 'ibtime_H:' , ibtime_H
  if (debugfdb) write(*,*) '-----------------------------------'
  numbwf=0

  do i=ibtime_H,ibtime_H+ideltas/3600
    ltim=i
    ldat=ibdate
    if (i .ge. 24) then 
      ltim=ltim-INT(i/24)*24
      ldat=ldat+INT(i/24)
    end if
    if (debugfdb) WRITE(*,*) 'ltim:' ,ltim,'ldat:' ,ldat
    jul=juldate(ldat,ltim*10000)
    if (debugfdb) WRITE(*,*) 'jul:' , jul
    if ((jul.ge.beg).and.(jul.le.end)) then
      numbwf=numbwf+1
      if (numbwf.gt.maxwf) then      ! check exceedance of dimension
        write(*,*) 'Number of wind fields needed is too great.'
        write(*,*) 'Reduce modelling period (file "COMMAND") or'
        write(*,*) 'reduce number of wind fields (file "AVAILABLE").'
        stop
      endif

      wftime1(numbwf)=nint((jul-bdate)*86400._dp)
      if (MOD(ltim, 6) .gt. 0) then
        wfstep1(numbwf)=MOD(ltim, 6)
        wfdate1(numbwf)=ldat
        wfforecasttime1(numbwf)=INT(ltim/6)*6
        write(wfdatetime1(numbwf)(1:8),'(I8)') ldat
      else if (MOD(ltim, 6) .eq. 0) then
        wfstep1(numbwf)=6
        if (ltim .eq. 0) then
          wfdate1(numbwf)=ldat-1
          wfforecasttime1(numbwf)=18
        else
          wfdate1(numbwf)=ldat
          wfforecasttime1(numbwf)=INT(ltim/6)*6-6
        endif
        write(wfdatetime1(numbwf)(1:8),'(I8)') wfdate1(numbwf)
      endif

      write(wfdatetime1(numbwf)(9:10),'(I2.2)')  wfforecasttime1(numbwf)
      wfdatetime1(numbwf)(11:12)='00'

      if (debugfdb) write(*,*) 'wftime1(numbwf)=', wftime1(numbwf)
      if (debugfdb) write(*,*) 'wfforecasttime1(numbwf)=', wfforecasttime1(numbwf)
      if (debugfdb) write(*,*) 'wfstep1(numbwf)=', wfstep1(numbwf)
      if (debugfdb) write(*,*) 'wfdate1(numbwf)=', wfdate1(numbwf)
      if (debugfdb) write(*,*) 'wfdatetime1(numbwf)=', wfdatetime1(numbwf)
      if (debugfdb) write(*,*) '-----------------------------------'
    endif
  end do

  ! Open the wind field availability file and read available wind fields
  ! within the modelling period (nested grids)
  !*********************************************************************

!   do k=1,numbnests
!   !print*,length(numpath+2*(k-1)+1),length(numpath+2*(k-1)+2),length(4),length(3)
!   !print*,path(numpath+2*(k-1)+2)(1:length(numpath+2*(k-1)+2))
!     open(unitavailab,file=path(numpath+2*(k-1)+2) &
!          (1:length(numpath+2*(k-1)+2)),status='old',err=998)

!     do i=1,3
!       read(unitavailab,*)
!     end do

!     numbwfn(k)=0
! 700   read(unitavailab,'(i8,1x,i6,2(6x,a255))',end=699) ldat, &
!           !  ltim
!       jul=juldate(ldat,ltim)
!       if ((jul.ge.beg).and.(jul.le.end)) then
!         numbwfn(k)=numbwfn(k)+1
!         if (numbwfn(k).gt.maxwf) then      ! check exceedance of dimension
!        write(*,*) 'Number of nested wind fields is too great.'
!        write(*,*) 'Reduce modelling period (file "COMMAND") or'
!        write(*,*) 'reduce number of wind fields (file "AVAILABLE").'
!           stop
!         endif

!         wftime1n(k,numbwfn(k))=nint((jul-bdate)*86400._dp)
!       endif
!       goto 700       ! next wind field

! 699   continue

!     close(unitavailab)
!   end do


  ! Check wind field times of file AVAILABLE (expected to be in temporal order)
  !****************************************************************************

  if (numbwf.eq.0) then
    write(*,*) ' #### FLEXPART MODEL ERROR! NO WIND FIELDS    #### '
    write(*,*) ' #### AVAILABLE FOR SELECTED TIME PERIOD.     #### '
    stop
  endif

  do i=2,numbwf
    if (wftime1(i).le.wftime1(i-1)) then
      write(*,*) 'FLEXPART ERROR: FILE AVAILABLE IS CORRUPT.'
      write(*,*) 'THE WIND FIELDS ARE NOT IN TEMPORAL ORDER.'
      ! write(*,*) 'PLEASE CHECK FIELD ',wfname1(i)
      stop
    endif
  end do

  ! Check wind field times of file AVAILABLE for the nested fields
  ! (expected to be in temporal order)
  !***************************************************************

  do k=1,numbnests
    if (numbwfn(k).eq.0) then
      write(*,*) '#### FLEXPART MODEL ERROR! NO WIND FIELDS  ####'
      write(*,*) '#### AVAILABLE FOR SELECTED TIME PERIOD.   ####'
      stop
    endif

    do i=2,numbwfn(k)
      if (wftime1n(k,i).le.wftime1n(k,i-1)) then
      write(*,*) 'FLEXPART ERROR: FILE AVAILABLE IS CORRUPT. '
      write(*,*) 'THE NESTED WIND FIELDS ARE NOT IN TEMPORAL ORDER.'
      ! write(*,*) 'PLEASE CHECK FIELD ',wfname1n(k,i)
      write(*,*) 'AT NESTING LEVEL ',k
      stop
      endif
    end do

  end do


  ! For backward trajectories, reverse the order of the windfields
  !***************************************************************

  if (ideltas.ge.0) then
    do i=1,numbwf
      wftime(i)=wftime1(i)
      wfdatetime(i)=wfdatetime1(i)
      wfstep(i)=wfstep1(i)
    end do
    do k=1,numbnests
      do i=1,numbwfn(k)
        wftimen(k,i)=wftime1n(k,i)
      end do
    end do
  else
    do i=1,numbwf
      wftime(numbwf-i+1)=wftime1(i)
      wfdatetime(numbwf-i+1)=wfdatetime1(i)
      wfstep(numbwf-i+1)=wfstep1(i)
    end do
    do k=1,numbnests
      do i=1,numbwfn(k)
        wftimen(k,numbwfn(k)-i+1)=wftime1n(k,i)
      end do
    end do
  endif

  ! Check the time difference between the wind fields. If it is big,
  ! write a warning message. If it is too big, terminate the trajectory.
  !*********************************************************************

  do i=2,numbwf
    idiff=abs(wftime(i)-wftime(i-1))
    if (idiff.gt.idiffmax.and.lroot) then
      write(*,*) 'FLEXPART WARNING: TIME DIFFERENCE BETWEEN TWO'
      write(*,*) 'WIND FIELDS IS TOO BIG FOR TRANSPORT CALCULATION.&
            &'
      write(*,*) 'THEREFORE, TRAJECTORIES HAVE TO BE SKIPPED.'
    else if (idiff.gt.idiffnorm.and.lroot.and.lwarntd) then
      write(*,*) 'FLEXPART WARNING: TIME DIFFERENCE BETWEEN TWO'
      write(*,*) 'WIND FIELDS IS BIG. THIS MAY CAUSE A DEGRADATION'
      write(*,*) 'OF SIMULATION QUALITY.'
      lwarntd=.false. ! only issue this warning once
    endif
  end do

  do k=1,numbnests
    if (numbwfn(k).ne.numbwf) then
      write(*,*) 'FLEXPART ERROR: THE AVAILABLE FILES FOR THE'
      write(*,*) 'NESTED WIND FIELDS ARE NOT CONSISTENT WITH'
      write(*,*) 'THE AVAILABLE FILE OF THE MOTHER DOMAIN.  '
      write(*,*) 'ERROR AT NEST LEVEL: ',k
      stop
    endif
    do i=1,numbwf
      if (wftimen(k,i).ne.wftime(i)) then
        write(*,*) 'FLEXPART ERROR: THE AVAILABLE FILES FOR THE'
        write(*,*) 'NESTED WIND FIELDS ARE NOT CONSISTENT WITH'
        write(*,*) 'THE AVAILABLE FILE OF THE MOTHER DOMAIN.  '
        write(*,*) 'ERROR AT NEST LEVEL: ',k
        stop
      endif
    end do
  end do

  ! Reset the times of the wind fields that are kept in memory to no time
  !**********************************************************************

  do i=1,2
    memind(i)=i
    memtime(i)=999999999
  end do

  return

998   write(*,*) ' #### FLEXPART MODEL ERROR! AVAILABLE FILE   #### '
  write(*,'(a)') '     '//path(numpath+2*(k-1)+2) &
        (1:length(numpath+2*(k-1)+2))
  write(*,*) ' #### CANNOT BE OPENED             #### '
  stop

999   write(*,*) ' #### FLEXPART MODEL ERROR! AVAILABLE FILE #### '
  write(*,'(a)') '     '//path(4)(1:length(4))
  write(*,*) ' #### CANNOT BE OPENED           #### '
  stop

end subroutine get_fdbtimes
