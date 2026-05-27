package com.truthstream.eureka;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

/**
 * TruthStream Eureka Registry Server.
 *
 * <p>Runs the Netflix Eureka service registry. Both the Spring Boot Gateway
 * (truthstream-gateway) and the FastAPI AI Service (truthstream-ai-service)
 * register with this server so they can discover each other dynamically.
 *
 * <p>Dashboard: https://&lt;host&gt;:&lt;port&gt;/
 * Health:    https://&lt;host&gt;:&lt;port&gt;/actuator/health
 */
@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
