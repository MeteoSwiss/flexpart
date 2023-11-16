!*******************************************************************************
!                                                                              *
!      Input file for the Lagrangian particle dispersion model FLEXPART        *
!                       Please specify your output grid                        *
!                                                                              *
! OUTLON0    = GEOGRAPHYICAL LONGITUDE OF LOWER LEFT CORNER OF OUTPUT GRID     *
! OUTLAT0    = GEOGRAPHYICAL LATITUDE OF LOWER LEFT CORNER OF OUTPUT GRID      *
! NUMXGRID   = NUMBER OF GRID POINTS IN X DIRECTION (= No. of cells + 1)       *
! NUMYGRID   = NUMBER OF GRID POINTS IN Y DIRECTION (= No. of cells + 1)       *
! DXOUT      = GRID DISTANCE IN X DIRECTION                                    *
! DYOUN      = GRID DISTANCE IN Y DIRECTION                                    *
! OUTHEIGHTS = HEIGHT OF LEVELS (UPPER BOUNDARY)                               *
!*******************************************************************************
&OUTGRID
 OUTLON0=   -179.50, ! GEOGRAPHYICAL LONGITUDE OF LOWER LEFT CORNER OF OUTPUT GRID
 OUTLAT0=    -90.00, ! GEOGRAPHYICAL LATITUDE OF LOWER LEFT CORNER OF OUTPUT GRID
 NUMXGRID=     1440, ! NUMBER OF GRID POINTS IN X DIRECTION (= No. of cells + 1)
 NUMYGRID=      720, ! NUMBER OF GRID POINTS IN Y DIRECTION (= No. of cells + 1)
 DXOUT=        0.25, ! GRID DISTANCE IN X DIRECTION
 DYOUT=        0.25, ! GRID DISTANCE IN Y DIRECTION
 OUTHEIGHTS=  500.0, 2000, 10000 ! HEIGHT OF LEVELS (UPPER BOUNDARY)
 /
