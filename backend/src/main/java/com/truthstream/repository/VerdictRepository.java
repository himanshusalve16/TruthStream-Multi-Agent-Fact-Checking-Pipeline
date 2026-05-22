package com.truthstream.repository;

import com.truthstream.model.Verdict;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface VerdictRepository extends JpaRepository<Verdict, UUID> {
    List<Verdict> findByJobId(UUID jobId);
    Optional<Verdict> findByJobIdAndIsOverallTrue(UUID jobId);
    List<Verdict> findByJobIdAndIsOverallFalse(UUID jobId);
}
