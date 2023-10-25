MODULE timer_mod

    USE OMP_LIB

    implicit none

    INTEGER, PARAMETER     :: active_timers_max=32       ! max number of simultaneously active timers
    INTEGER                :: active_timers(active_timers_max), &   ! initialization in "init"
                              active_timers_top
    TYPE t_timer
        LOGICAL           :: reserved         ! usage flag
        LOGICAL           :: active           ! started flag
        CHARACTER(len=30) :: description      ! description of timer
        DOUBLE PRECISION  :: start, end, tot  ! start time, end time, total time
        integer           :: calls            ! number of calls to timer, accumulated total time
        INTEGER           :: active_under     ! ID of superordinate timer; -1: "undefined", 0: "none", >0: id
    END TYPE t_timer

    TYPE(t_timer), PARAMETER :: t_init = t_timer(.FALSE., .FALSE., 'noname', 0.0, 0.0, 0.0, 0, -1)

    !********************************************************
    ! Variables defining timers
    !********************************************************

    INTEGER, PARAMETER :: timer_max = 100
    INTEGER, PARAMETER :: timer_verbosity = 0 ! 0 = No messages, 1 for timer debugging messages

    INTEGER :: timer_total, timer_readwind_request, timer_readwind_iter, &
    &          timer_readwind_fdb_inloop, timer_readwind_loop, timer_readwind_common, &
    &          timer_fdb_request_datetime, timer_fdb_create_request_dr, &
    &          timer_fdb_datareader_open,timer_fdb_get_max_message_len, &
    &          timer_allocate_buf, timer_fdb_datareader_tell, &
    &          timer_fdb_setup_request, timer_fdb_new_dr, timer_fdb_retrieve, &
    &          timer_fdb_datareader_read

    INTEGER :: timer_top = 1

    TYPE(t_timer), SAVE   :: timers(timer_max)

    contains

    INTEGER FUNCTION new_timer(text) RESULT(timer_id)
        implicit none
        CHARACTER(len=*), INTENT(in)    :: text
        timer_id = timer_top
        timers(timer_id) = t_init
        timers(timer_id)%reserved = .TRUE.
        timers(timer_id)%description = adjustl(text)

        timer_top = timer_top + 1
        if (timer_verbosity .eq. 1) then
            write(*,*) 'TIMER ID: ', timer_id, ' TIMER DESC: ', timers(timer_id)%description
        end if
        return

    END FUNCTION new_timer

    subroutine start_timer(timer_id)
        implicit none
        integer, intent(in) :: timer_id 
        DOUBLE PRECISION :: start
        integer :: it_sup
        timers(timer_id)%active = .TRUE.

        ! call-hierarchy bookkeeping: set <active_under>
        ! The actual superordinate timer is always active_timers(active_timers_top).
        it_sup = active_timers(active_timers_top)
        IF (timers(timer_id)%active_under /= it_sup  .AND.  timers(timer_id)%active_under /= 0) THEN
          IF (timers(timer_id)%active_under == -1) THEN
            timers(timer_id)%active_under = it_sup            ! first start of this timer at all
          ELSE
            timers(timer_id)%active_under = 0                 ! this timer has been called by different
          ENDIF                                     !   superordinate timers, set to top for the printout
        ENDIF
    
        ! call hierarchy bookkeeping: set <active_timers>
        active_timers_top = active_timers_top + 1
        IF (active_timers_top > active_timers_max) &
             CALL timer_abort(timer_id,'timer_start: number of simultaneously active timers higher than ''active_timers_max''')
        active_timers(active_timers_top) = timer_id

        start = omp_get_wtime(); 
        if (timer_verbosity .eq. 1) then
            write(*,*) 'Starting TIMER: ', timers(timer_id)%description, ' TIME: ', start
        end if
        timers(timer_id)%start = start

    end subroutine start_timer

    subroutine stop_timer(timer_id)

        implicit none
        integer, intent(in) :: timer_id
        DOUBLE PRECISION :: end_time, tot

        end_time = omp_get_wtime(); 
        timers(timer_id)%end = end_time
        tot = timers(timer_id)%end - timers(timer_id)%start 
        timers(timer_id)%tot = timers(timer_id)%tot + tot
        timers(timer_id)%calls = timers(timer_id)%calls + 1

        ! timer hierarchy bookkeeping
        ! timer intervals need to be nested
        IF (active_timers(active_timers_top) /= timer_id) &
            CALL timer_abort(timer_id,'timer_stop: a subsidary timer is still active, stop that first')
        active_timers_top = active_timers_top - 1

        if (timer_verbosity .eq. 1) then
            write(*,*) 'Stopping TIMER: ', timers(timer_id)%description, ' TIME: ', end_time, ' ELAPSED: ', tot
        end if

    end subroutine stop_timer

    subroutine print_timers()

        implicit none
        integer :: it
        print*,''
        print*,''
        print*, '|---------------------------------|------------------------------|-------------|------------------------------|'
        print*, '|              Timer              |       Elapsed Time (avg)     |  Num Calls  |           Total Time         |'
        print*, '|---------------------------------|------------------------------|-------------|------------------------------|'
        DO it = 1, timer_top
            IF (timers(it)%active .eqv. .TRUE. .AND. timers(it)%active_under == 0) THEN
                CALL print_report_hierarchical(it, 0)! print top-level timers hierarchical
            ENDIF
        ENDDO
        print*, '|---------------------------------|------------------------------|-------------|------------------------------|'

    end subroutine print_timers


  !
  ! print statistics for timer <it> and all of its sub-timers
  !
    RECURSIVE SUBROUTINE print_report_hierarchical(it, nd)

        INTEGER, INTENT(IN) :: it
        INTEGER, INTENT(IN) :: nd            !<  nesting depth

        INTEGER :: n                         ! number of sub-timers
        INTEGER :: subtimer_list(timer_top)  ! valid entries: 1..n
        INTEGER :: k

        CALL print_timer(it, nd)

        n = 0
        DO k=1,timer_top
        IF (timers(k)%active_under == it) THEN
            n = n+1
            subtimer_list(n) = k
        ENDIF
        END DO

        ! print subtimers
        DO k=1,n
        CALL print_report_hierarchical(subtimer_list(k), nd+1)
        ENDDO

    END SUBROUTINE print_report_hierarchical

    subroutine print_timer(n, nd)

        implicit none
        integer, intent(in) :: n, nd
        CHARACTER(len=33) :: hierarchy_str=''

        hierarchy_str(1:1+nd)=repeat('-',nd)
        hierarchy_str(nd+1:)=timers(n)%description

        WRITE(*,*) '|', hierarchy_str, '|',  &
        & time_sec_str(timers(n)%tot/timers(n)%calls) ,'|', timers(n)%calls,'|', &
        & time_sec_str(timers(n)%tot),'|'
    end subroutine print_timer

    SUBROUTINE timer_abort(it,reason)
        INTEGER,          INTENT(in), OPTIONAL :: it
        CHARACTER(len=*), INTENT(in), OPTIONAL :: reason
    
        WRITE (*,*)  'Error in module timer_mod:'
        IF (PRESENT(it)) THEN
          WRITE (*,*) 'timer handle: ', it
          IF (it < 1 .OR. it > timer_top) THEN
            WRITE (*,*) 'timer name: unspecified'
        ELSE
            WRITE (*,*) 'timer name: ', TRIM(timers(it)%description)
          ENDIF
        ENDIF
        IF (PRESENT(reason)) THEN
          WRITE (*,*) '            ', reason
        ENDIF

        stop
        
    END SUBROUTINE timer_abort

    CHARACTER(len=30) FUNCTION time_sec_str(ts)
        implicit none
        DOUBLE PRECISION, INTENT(in) :: ts
        integer, parameter :: dp=kind(0.d0)  ! double precision

        IF (ts < 0.0_dp) THEN
            time_sec_str="    ??????"
        ELSE IF(ts < 1._dp) THEN
            WRITE(time_sec_str,'(e30.3)') ts
        ELSE IF(ts < 1.e1_dp) THEN
            WRITE(time_sec_str,'(f30.4)') ts
        ELSE IF(ts < 1.e2_dp) THEN
            WRITE(time_sec_str,'(f30.3)') ts
        ELSE IF(ts < 1.e3_dp) THEN
            WRITE(time_sec_str,'(f30.2)') ts
        ELSE IF(ts < 1.e4_dp) THEN
            WRITE(time_sec_str,'(f30.1)') ts
        ELSE
            WRITE(time_sec_str,'(f30.0)') ts
        ENDIF

    END FUNCTION time_sec_str

end module timer_mod
