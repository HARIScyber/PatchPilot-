export interface Project {
  id: string;
  name: string;
  bug_description?: string;
  stack_trace?: string;
  language: string;
  workspace_path?: string;
  file_count: number;
  size_bytes: number;
  analysis_status: 'pending' | 'analyzing' | 'analyzed' | 'failed';
  created_at: string;
}

export interface FileItem {
  path: string;
  name: string;
  extension: string;
  size_bytes: number;
  directory: string;
}

export interface Finding {
  id: string;
  finding_type: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  file_path: string;
  line_number?: number;
  title: string;
  description: string;
  code_snippet?: string;
  confidence: number;
  recommended_action?: string;
}

export interface RepairPlan {
  id: string;
  problem_summary: string;
  root_cause: string;
  evidence?: string;
  candidate_files: string[];
  proposed_changes: string[];
  expected_behavior: string;
  regression_test_plan?: string;
  risks_and_assumptions?: string;
  created_at: string;
}

export interface Patch {
  id: string;
  project_id: string;
  plan_id?: string;
  target_file: string;
  diff_content: string;
  validation_status: 'pending' | 'valid' | 'invalid' | 'rejected';
  validation_error?: string;
  is_approved: boolean;
  is_applied: boolean;
  created_at: string;
}

export interface GeneratedTest {
  id: string;
  project_id: string;
  patch_id?: string;
  test_file_path: string;
  test_code: string;
  test_framework: string;
  test_purpose?: string;
  execution_status: string;
}

export interface VerificationRun {
  id: string;
  project_id: string;
  patch_id?: string;
  status: string;
  verification_status:
    | 'VERIFIED_AGAINST_DEFINED_TESTS'
    | 'TESTS_FAILED'
    | 'PARTIALLY_VERIFIED'
    | 'NOT_VERIFIED'
    | 'EXECUTION_UNAVAILABLE'
    | 'REQUIRES_HUMAN_REVIEW';
  baseline_passed?: boolean | null;
  baseline_exit_code?: number;
  baseline_stdout?: string;
  baseline_stderr?: string;
  patched_passed?: boolean | null;
  patched_exit_code?: number;
  patched_stdout?: string;
  patched_stderr?: string;
  regression_test_passed?: boolean;
  regression_test_stdout?: string;
  duration_seconds: number;
}

export interface AuditEvent {
  id: string;
  project_id?: string;
  event_type: string;
  title: string;
  created_at: string;
}

export interface EvidenceReport {
  meta: {
    report_id: string;
    generated_at: string;
    agent: string;
    ai_provider: string;
  };
  project: {
    id: string;
    name: string;
    bug_description?: string;
    stack_trace?: string;
    file_count: number;
    size_bytes: number;
  };
  investigation: {
    findings_count: number;
    findings: Finding[];
  };
  ai_hypothesis: {
    problem_summary?: string;
    root_cause?: string;
    proposed_changes: string[];
    expected_behavior?: string;
  };
  patch_details: {
    patch_id?: string;
    target_file?: string;
    diff_content?: string;
    validation_status?: string;
    is_approved: boolean;
    is_applied: boolean;
  };
  regression_testing: {
    tests_generated: number;
    test_suites: Array<{
      file: string;
      framework: string;
      purpose?: string;
      code: string;
    }>;
  };
  verification_evidence: {
    verification_status: string;
    baseline_execution: {
      passed?: boolean;
      exit_code?: number;
      stdout_excerpt: string;
    };
    patched_execution: {
      passed?: boolean;
      exit_code?: number;
      stdout_excerpt: string;
      stderr_excerpt: string;
      duration_seconds: number;
    };
  };
  timeline: Array<{
    timestamp: string;
    event_type: string;
    title: string;
  }>;
}

export interface EvaluationResults {
  metadata: {
    timestamp: string;
    benchmark_dataset: string;
    total_evaluated_cases: number;
  };
  metrics_comparison: {
    static_analysis_baseline: {
      localization_recall_at_1: number;
      patch_application_rate: number;
      test_pass_rate: number;
      avg_attempts: number;
      mean_execution_time_seconds: number;
    };
    single_pass_ai_repair: {
      localization_recall_at_1: number;
      patch_application_rate: number;
      test_pass_rate: number;
      avg_attempts: number;
      mean_execution_time_seconds: number;
    };
    patchpilot_closed_loop: {
      localization_recall_at_1: number;
      patch_application_rate: number;
      test_pass_rate: number;
      avg_attempts: number;
      mean_execution_time_seconds: number;
    };
  };
  conclusion: string;
}
