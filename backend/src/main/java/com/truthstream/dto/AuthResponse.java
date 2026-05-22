package com.truthstream.dto;

import lombok.Builder;
import lombok.Data;

import java.util.UUID;

@Data
@Builder
public class AuthResponse {
    private UUID userId;
    private String email;
    private String accessToken;
    private String tokenType;
    private long expiresIn;
}
