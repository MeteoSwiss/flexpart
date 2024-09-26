!******************************************************************************
!*                                                                            *
!*      Input file for the Lagrangian particle dispersion model FLEXPART      *
!*                       Please specify your output grid                      *
!*                                                                            *
!******************************************************************************
&OUTGRID
 OUTLON0=         -10.000, ! Geographical longitude of lower left corner of output grid
 OUTLAT0=          35.000, ! Geographical latitude of lower left corner of output grid
 NUMXGRID=            570, ! Number of grid points in x direction (= No. of cells + 1)
 NUMYGRID=            300, ! Number of grid points in y direction (= No. of cells + 1)
 DXOUT=              0.10, ! Grid distance in x direction
 DYOUT=              0.10, ! Grid distance in y direction
 OUTHEIGHTS=500,2000,10000 ! Height of levels (upper boundary)
/
