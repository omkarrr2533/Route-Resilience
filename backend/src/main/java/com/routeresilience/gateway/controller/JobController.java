package com.routeresilience.gateway.controller;

import com.routeresilience.gateway.jobs.ApproxBetweennessRequest;
import com.routeresilience.gateway.jobs.Job;
import com.routeresilience.gateway.jobs.JobService;
import com.routeresilience.gateway.jobs.JobView;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

/**
 * Async job API. Submit an expensive analysis, get a job id back immediately (202), then poll
 * status until the result lands — the request thread never blocks on minutes-long compute.
 */
@RestController
@RequestMapping("/api/jobs")
public class JobController {

    private final JobService jobs;

    public JobController(JobService jobs) {
        this.jobs = jobs;
    }

    /** Submit an approximate-betweenness job. An empty body runs the defaults. */
    @PostMapping("/approx-betweenness")
    public ResponseEntity<JobView> submitApprox(@RequestBody(required = false) ApproxBetweennessRequest req) {
        if (req == null) {
            req = new ApproxBetweennessRequest(null, null, null, null, null, null);
        }
        Job job = jobs.submitApprox(req);
        return ResponseEntity.accepted().body(job.toView());   // 202 + the polling handle
    }

    @GetMapping("/{id}")
    public JobView get(@PathVariable String id) {
        return jobs.get(id).map(Job::toView)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "no such job: " + id));
    }

    @GetMapping
    public List<JobView> all() {
        return jobs.all().stream().map(Job::toView).toList();
    }
}
