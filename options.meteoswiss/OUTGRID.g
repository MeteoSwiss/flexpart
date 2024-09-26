!*******************************************************************************
!*                                                                             *
!*      Input file for the Lagrangian particle dispersion model FLEXPART       *
!*                       Please specify your output grid                       *
!*                                                                             *
!*******************************************************************************
&OUTGRID
 OUTLON0=         -179.50, ! Geographical longitude of lower left corner of output grid
 OUTLAT0=          -90.00, ! Geographical latitude of lower left corner of output grid
 NUMXGRID=           1440, ! Number of grid points in x direction (= No. of cells + 1)
 NUMYGRID=            720, ! Number of grid points in y direction (= No. of cells + 1)
 DXOUT=              0.25, ! Grid distance in x direction
 DYOUT=              0.25, ! Grid distance in y direction
 OUTHEIGHTS=500,2000,10000 ! Height of levels (upper boundary)
/
