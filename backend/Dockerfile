# Multi-stage build: fat-jar with Maven, then run on a slim JRE so the final image stays small.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
# Resolve dependencies first against the bare pom so this layer caches across code changes.
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --from=build /build/target/gateway-*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
