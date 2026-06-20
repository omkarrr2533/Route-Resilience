package com.routeresilience.gateway.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** CORS for the vanilla dashboard when it's served separately from the gateway (Live Server,
 *  a static host, etc.). Read-only API, so GET is all we open up. */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5500", "http://127.0.0.1:5500",
                                "http://localhost:8000", "http://localhost:3000")
                .allowedMethods("GET");
    }
}
