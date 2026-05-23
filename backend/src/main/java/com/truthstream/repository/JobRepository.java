package com.truthstream.repository;

import com.truthstream.model.Job;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface JobRepository extends JpaRepository<Job, UUID> {

    @Query("SELECT j FROM Job j WHERE j.user.id = :userId ORDER BY j.createdAt DESC")
    Page<Job> findByUserIdOrderByCreatedAtDesc(@Param("userId") UUID userId, Pageable pageable);

    @Query("""
            SELECT j FROM Job j
            WHERE j.user.id = :userId
              AND j.status = :status
              AND j.inputUrl = :inputUrl
              AND j.createdAt > :since
            ORDER BY j.createdAt DESC
            """)
    Optional<Job> findFirstByUserIdAndStatusAndInputUrlAndCreatedAtAfter(
            @Param("userId") UUID userId,
            @Param("status") String status,
            @Param("inputUrl") String inputUrl,
            @Param("since") OffsetDateTime since);

    @Modifying
    @Transactional
    @Query("UPDATE Job j SET j.status = :status, j.updatedAt = CURRENT_TIMESTAMP WHERE j.id = :id")
    void updateStatus(@Param("id") UUID id, @Param("status") String status);

    @Modifying
    @Transactional
    @Query("UPDATE Job j SET j.status = :status, j.errorMessage = :msg, j.updatedAt = CURRENT_TIMESTAMP WHERE j.id = :id")
    void updateStatusAndError(@Param("id") UUID id,
                              @Param("status") String status,
                              @Param("msg") String errorMessage);
}
