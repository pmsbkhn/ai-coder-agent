package com.example.library.catalog;

import com.example.library.common.DomainException;

public class Copy {
    private final String id;
    private CopyStatus status;

    public Copy(String id) {
        this.id = id;
        this.status = CopyStatus.AVAILABLE;
    }

    public String getId() {
        return id;
    }

    public CopyStatus getStatus() {
        return status;
    }

    // Internal method to change status - only used by domain operations
    void setStatus(CopyStatus status) {
        this.status = status;
    }

    // Domain-controlled operation to loan the copy
    public void loan() {
        if (status != CopyStatus.AVAILABLE) {
            throw new DomainException(DomainException.Code.COPY_NOT_AVAILABLE, "Copy is not available for loan");
        }
        status = CopyStatus.ON_LOAN;
    }

    // Domain-controlled operation to return the copy
    public void returnCopy() {
        if (status != CopyStatus.ON_LOAN) {
            throw new DomainException(DomainException.Code.LOAN_ALREADY_RETURNED, "Loan already returned");
        }
        status = CopyStatus.AVAILABLE;
    }

    // For testing purposes
    public void markAsLost() {
        this.status = CopyStatus.LOST;
    }
}