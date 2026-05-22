package com.truthstream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class TruthStreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(TruthStreamApplication.class, args);
    }
}
