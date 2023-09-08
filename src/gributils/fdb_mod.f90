MODULE fdb_mod

    !*****************************************************************
    !                                                                *
    !  This is a module for providing access to the                  *
    !  metadata and data within a GRIB messages stored in FDB.       *
    !                                                                *
    !                                                                *
    !*****************************************************************

    use grib_api
    use par_mod
    use com_mod
    use fdb
    use class_gribfile
    use timer_mod
    
    IMPLICIT NONE
    PRIVATE   ! The default is that everything is private, unless
              ! specified otherwise

    ! Note that all public interfaces and variables should have a
    ! FDB_ prefix

    PUBLIC :: fdb_create_request_dr
    PUBLIC :: fdb_grib_centre
    PUBLIC :: fdb_get_max_message_len

CONTAINS
    
    SUBROUTINE fdb_create_request_dr(forecastDateTime, step, dr, req, caller)
        character(len=*), OPTIONAL, INTENT(IN) :: caller
        TYPE(c_ptr), INTENT(OUT) :: dr !fdb datareader
        type(c_ptr), INTENT(OUT) :: req !fdb request
        INTEGER, INTENT(IN) :: step
        CHARACTER(len=12), INTENT(IN) :: forecastDateTime ! Used to store string values to form fdb request
        CHARACTER(len=32) :: step_str ! Used to store string values to form fdb request
        INTEGER(kind=c_int) :: res !fdb response

        character(len=3) :: productionStatusOfProcessedData(2)
        character(len=6) :: typeOfLevel(3)
        character(len=6) :: level(140)
        character(len=6) :: parameterNumber(15)
        character(len=3) :: parameterCategory(8)
        character(len=3) :: discipline(3)

        if (caller == 'readwind') call start_timer(timer_fdb_setup_request)
        res = fdb_new_request(req)

        call fdb_request_add_values(req, "dataDate", [forecastDateTime(1:8)])
        call fdb_request_add_values(req, "dataTime", [forecastDateTime(9:12)])

        write(step_str, '(I2)')  step
        call fdb_request_add_values(req, "endStep", [adjustl(trim(step_str))])

        productionStatusOfProcessedData(1)="0"
        productionStatusOfProcessedData(2)="255"
        call fdb_request_add_values(req, "productionStatusOfProcessedData", productionStatusOfProcessedData)

        call fdb_request_add_values(req, "productDefinitionTemplateNumber", ["0","8"])

        parameterNumber(1)='0'
        parameterNumber(2)='1'
        parameterNumber(3)='2'
        parameterNumber(4)='3'
        parameterNumber(5)='4'
        parameterNumber(6)='6'
        parameterNumber(7)='9'
        parameterNumber(8)='10'
        parameterNumber(9)='11'
        parameterNumber(10)='32'
        parameterNumber(11)='37'
        parameterNumber(12)='38'
        parameterNumber(13)='142'
        parameterNumber(14)='160'
        parameterNumber(15)='254'
        call fdb_request_add_values(req, "parameterNumber", parameterNumber)

        call fdb_request_add_values(req, "generatingProcessIdentifier", ["154"])
        
        discipline(1)='0'
        discipline(2)='2'
        discipline(3)='192'
        call fdb_request_add_values(req, "discipline", discipline)

        parameterCategory(1)='0'
        parameterCategory(2)='1'
        parameterCategory(3)='2'
        parameterCategory(4)='3'
        parameterCategory(5)='4'
        parameterCategory(6)='5'
        parameterCategory(7)='6'
        parameterCategory(8)='128'
        call fdb_request_add_values(req, "parameterCategory", parameterCategory)

        typeOfLevel(1)="sfc" !surface, heightAboveGround
        typeOfLevel(2)="ml" !hybrid
        typeOfLevel(3)="10" !entireAtmosphereLayer
        call fdb_request_add_values(req, "typeOfFirstFixedSurface", typeOfLevel)

        call expand_values_for_request(level,0,140)
        call fdb_request_add_values(req, "level", level)

        if (caller == 'readwind') call stop_timer(timer_fdb_setup_request)

        if (caller == 'readwind') call start_timer(timer_fdb_new_dr)
        write(*,*) 'Reading from FDB (dataDate, dataTime, step):', forecastDateTime(1:8), &
        &  ' ', forecastDateTime(9:12), ' ', step_str
        
        res = fdb_new_datareader(dr);
        if (caller == 'readwind') call stop_timer(timer_fdb_new_dr)

        if (caller == 'readwind') call start_timer(timer_fdb_retrieve)
        res = fdb_retrieve(fdb_handle, req, dr)
        if (caller == 'readwind') call stop_timer(timer_fdb_retrieve)

    END SUBROUTINE

    SUBROUTINE fdb_get_max_message_len(req, it, max_len)
        type(c_ptr), INTENT(IN)                         :: req !fdb request
        integer(kind=c_int), INTENT(OUT)                :: max_len 
        type(c_ptr), INTENT(IN)                         :: it ! ListIterator
        character(kind=c_char, len=1), dimension(100)   :: uri
        integer(kind=c_int)                             :: err, res, off, len
        logical(kind=c_bool)                            :: duplicates = .false.

        res = fdb_list(fdb_handle, req, it, duplicates)
        err = fdb_listiterator_next(it)
        do while(err == 0) 
            res = fdb_listiterator_attrs(it, uri, off, len);
    
            err = fdb_listiterator_next(it)
    
            if (len > max_len) then
              max_len = len
            end if
        end do
        res = fdb_delete_listiterator(it)
    END SUBROUTINE

    INTEGER FUNCTION fdb_grib_centre(wftime_indj) RESULT(message_centre)
        INTEGER, INTENT(IN) :: wftime_indj
        INTEGER :: res, iret, igrib, grib_centre, status
        INTEGER :: validityDate, validityTime
        TYPE(c_ptr):: dr !fdb datareader
        integer(c_long) :: total_size, read, marker
        character(kind=c_char, len=1), dimension(:), allocatable  :: buf
        type(c_ptr) :: req !fdb request
        character(len=24) :: gribErrorMsg = 'Error getting grib center'

        call fdb_create_request_dr(wfdatetime(wftime_indj), wfstep(wftime_indj), dr, req)
        res = fdb_datareader_open(dr, total_size)

        allocate(buf(total_size))
        res = fdb_datareader_tell(dr, read);

        ! FIND CENTER OF GRIB MESSAGE
        marker = 2000
        res = fdb_datareader_read(dr, buf, marker, read)
        call codes_new_from_message(igrib, buf, status)
        call grib_get(igrib,'centre', grib_centre, iret)
        call grib_check(iret,'fdb_grib_centre',gribErrorMsg)
        call grib_release(igrib)

        deallocate(buf)

        res = fdb_delete_datareader(dr);

        IF (grib_centre == CENTRE_NCEP) THEN
            message_centre = GRIBFILE_CENTRE_NCEP
        ELSE IF (grib_centre == CENTRE_ECMWF) THEN
            message_centre = GRIBFILE_CENTRE_ECMWF
        ELSE
            message_centre = GRIBFILE_CENTRE_UNKNOWN
        END IF

    END FUNCTION

END MODULE fdb_mod
