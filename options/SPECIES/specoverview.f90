!**********************************************************************
! Copyright 1998,1999,2000,2001,2002,2005,2007,2008,2009,2010         *
! Andreas Stohl, Petra Seibert, A. Frank, Gerhard Wotawa,             *
! Caroline Forster, Sabine Eckhardt, John Burkhart, Harald Sodemann   *
!                                                                     *
! This file is part of FLEXPART.                                      *
!                                                                     *
! FLEXPART is free software: you can redistribute it and/or modify    *
! it under the terms of the GNU General Public License as published by*
! the Free Software Foundation, either version 3 of the License, or   *
! (at your option) any later version.                                 *
!                                                                     *
! FLEXPART is distributed in the hope that it will be useful,         *
! but WITHOUT ANY WARRANTY; without even the implied warranty of      *
! MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the       *
! GNU General Public License for more details.                        *
!                                                                     *
! You should have received a copy of the GNU General Public License   *
! along with FLEXPART.  If not, see <http://www.gnu.org/licenses/>.   *
!**********************************************************************
program specoverview
  implicit none

  character(len=11) :: speciesfn
  character(len=3)  :: aspec
  character(len=16) :: pspecies
  real :: pdecay, pweta_gas, pwetb_gas, preldiff, phenry, pf0, pdensity, pdquer
  real :: pdsigma, pdryvel, pweightmolar, pohcconst, pohdconst, pohnconst
  real :: pcrain_aero, pcsnow_aero, pccn_aero, pin_aero
  real :: parea_dow(7), parea_hour(24), ppoint_dow(7), ppoint_hour(24)
  integer :: ierr, unitspecies, specnumber

  ! declare namelist
  namelist /species_params/ &
       pspecies, pdecay, pweta_gas, pwetb_gas, &
       pcrain_aero, pcsnow_aero, pccn_aero, pin_aero, &
       preldiff, phenry, pf0, pdensity, pdquer, &
       pdsigma, pdryvel, pweightmolar, pohcconst, pohdconst, pohnconst, &
       parea_dow, parea_hour, ppoint_dow, ppoint_hour

  unitspecies=4

  write(*,*) '    Species   |       |   WetDep(gas)   |    DryDep(gas)   |WetDep(below-C)| WetDep(in-C)|'// & 
             '     DryDepo(particles)  Alternative| Radioact.  |     OH Reaction      |'

  write(*,*) '    Name      |molwght| A          B    | D    H        f0 | Crain   Csnow |  ccn    in  |'// &
             '   rho    dquer    dsig       vd    | Halflife[s]|   C**     D[T]  N*** |'

  write(*,*) '--------------|-------|-----------------|------------------|---------------|-------------|'// &
             '------------------------------------|------------|----------------------|'


  do specnumber=1,100

     write (aspec,'(i0.3)') specnumber
     speciesfn='SPECIES_'//aspec

     ! write(*,*) 'Processing: ',speciesfn

     pspecies="" ! read failure indicator value
     pdecay=-9.9
     pweta_gas=-0.9E-09
     pwetb_gas=0.0
     pcrain_aero=-9.9
     pcsnow_aero=-9.9
     pccn_aero=-9.9
     pin_aero=-9.9
     preldiff=-9.9
     phenry=0.0
     pf0=0.0
     pdensity=-0.9E09
     pdquer=0.0
     pdsigma=0.0
     pdryvel=-9.99
     pohcconst=-9.9
     pohdconst=-9.9
     pohnconst=2.0
     pweightmolar=-9.9

     ! Open the SPECIES file and read species names and properties
     !************************************************************
     open(unitspecies,file=speciesfn,status='old',form='formatted',iostat=ierr)
     if (ierr /= 0) then
        ! Report missing files below 40
        if (specnumber <= 40) then
           write(*,'(i3,2(1x,a))') specnumber, 'no such file:', trim(speciesfn)
        end if
        cycle
     end if
     read(unitspecies,species_params)  ! to skip errors add: ,err=998
     close(unitspecies)

     write(*,45) specnumber,' ',pspecies,'|',pweightmolar,'|',pweta_gas,' ',pwetb_gas,'|', &
          preldiff,' ',phenry,' ',pf0,'|', &
          pcrain_aero,' ',pcsnow_aero,'|',pccn_aero,' ',pin_aero,'|', &
          pdensity,pdquer,pdsigma,pdryvel,'|',pdecay,'|',pohcconst,pohdconst,pohnconst,'|'

45   format(i3,a1,a11,a1,f7.1,a1,e8.1,a1,f8.2,a1, &
          f4.1,a1,e8.1,a1,f4.1,a1, &
          f7.1,a1,f7.1,a1,f6.1,a1,f6.1,a1, &
          e8.1,e9.1,f7.1,e12.3,a1,f12.1,a1,e8.1,f7.1,f7.1,a1)

998  continue
  enddo

  write(*,*) '** unit [cm^3/molec/s] (in FLEXPART version 9.2 and below this had unit [cm3/s], note the unit is now changed!)'
  write(*,*) '*** no unit'

  print*,'rho: density'

end program specoverview
