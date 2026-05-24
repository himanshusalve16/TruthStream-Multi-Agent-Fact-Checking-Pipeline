package com.truthstream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class TruthStreamApplication {
    private static final Logger logger = LoggerFactory.getLogger(TruthStreamApplication.class);

    public static void main(String[] args) {
        ApplicationContext ctx = SpringApplication.run(TruthStreamApplication.class, args);
        Environment env = ctx.getEnvironment();
        
        String port = env.getProperty("server.port");
        String[] profiles = env.getActiveProfiles();
        String activeProfile = profiles.length > 0 ? String.join(", ", profiles) : "default";
        
        String dbUrl = env.getProperty("spring.datasource.url");
        String redisHost = env.getProperty("spring.data.redis.host");
        String redisPort = env.getProperty("spring.data.redis.port");
        String fastApiUrl = env.getProperty("app.fastapi.base-url");

        logger.info("---------------------------------------------------------");
        logger.info("TruthStream Backend listening on port: {}", port);
        logger.info("Active Spring Profile(s): {}", activeProfile);
        logger.info("Datasource Target: {}", dbUrl);
        logger.info("Redis Target: {}:{}", redisHost, redisPort);
        logger.info("FastAPI Target: {}", fastApiUrl);
        logger.info("---------------------------------------------------------");
    }
}
