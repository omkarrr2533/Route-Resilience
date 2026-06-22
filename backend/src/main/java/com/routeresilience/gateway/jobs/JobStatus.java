package com.routeresilience.gateway.jobs;

/** Lifecycle of an async analysis job. */
public enum JobStatus {
    QUEUED, RUNNING, SUCCEEDED, FAILED
}
