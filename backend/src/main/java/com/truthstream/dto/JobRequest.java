package com.truthstream.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;
import org.hibernate.validator.constraints.URL;

@Data
public class JobRequest {

    @NotBlank(message = "input_type is required")
    @Pattern(regexp = "url|text", message = "input_type must be 'url' or 'text'")
    private String inputType;

    @URL(message = "Must be a valid URL")
    private String url;

    private String text;
}
