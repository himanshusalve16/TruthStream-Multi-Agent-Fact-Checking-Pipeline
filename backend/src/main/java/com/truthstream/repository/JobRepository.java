package com.truthstream.repository;

import com.truthstream.model.Job;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface JobRepository extends JpaRepository<Job, UUID> {

    Page<Job> findByUserIdOrderByCreatedAtDesc(UUID userId, Pageable pageable);

    @Query("""
        SELECT j FROM Job j
        WHERE j.user.id = :userId
          AND j.status = 'COMPLETE'
          AND j.inputUrl IS NOT NULL
          AND j.inputUrl = :url
          AND j.createdAt > :since
        ORDER BY j.createdAt DESC
        LIMIT 1
        """)
    Optional<Job> findRecentCompleteByUserAndUrl(
            @Param("userId") UUID userId,
            @Param("url") String url,
            @Param("since") OffsetDateTime since);

    @Modifying
    @Query("UPDATE Job j SET j.status = :status, j.updatedAt = NOW() WHERE j.id = :id")
    void updateStatus(@Param("id") UUID id, @Param("status") String status);

    @Modifying
    @Query("UPDATE Job j SET j.status = :status, j.errorMessage = :msg, j.updatedAt = NOW() WHERE j.id = :id")
    void updateStatusAndError(@Param("id") UUID id,
                              @Param("status") String status,
                              @Param("msg") String errorMessage);
}
