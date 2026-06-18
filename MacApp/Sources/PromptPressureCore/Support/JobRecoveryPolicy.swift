import Foundation

public enum JobRecoveryPolicy {
    public static func preferredJob(from jobs: [AppJob], currentID: String?) -> AppJob? {
        let ordered = jobs.sorted { lhs, rhs in
            if lhs.updatedAt == rhs.updatedAt {
                return lhs.createdAt > rhs.createdAt
            }
            return lhs.updatedAt > rhs.updatedAt
        }

        if let currentID,
           let current = ordered.first(where: { $0.id == currentID }),
           !current.status.isTerminal {
            return current
        }

        if let active = ordered.first(where: { !$0.status.isTerminal }) {
            return active
        }

        if let currentID,
           let current = ordered.first(where: { $0.id == currentID }) {
            return current
        }

        return ordered.first
    }

    public static func shouldStream(job: AppJob, streamingJobID: String?) -> Bool {
        !job.status.isTerminal && streamingJobID != job.id
    }
}
