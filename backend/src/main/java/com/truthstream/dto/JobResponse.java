package com.truthstream.dto;

import lombok.Builder;
import lombok.Data;

import java.time.OffsetDateTime;
import java.util.UUID;

@Data
@Builder
public class JobResponse {
    private UUID jobId;
    private String status;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
    private String inputUrl;
    private Integer claimsCount;
    private String verdict;
    private Double overallConfidence;
    private String errorMessage;
}
