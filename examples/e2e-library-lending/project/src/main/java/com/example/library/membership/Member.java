package com.example.library.membership;

import com.example.library.common.DomainException;
import java.util.Objects;

public class Member {
    private final String id;
    private final String name;
    private final int borrowLimit;
    private MemberStatus status;
    private int activeLoanCount;

    public Member(String id, String name) {
        this(id, name, 5); // Default borrow limit
    }

    public Member(String id, String name, int borrowLimit) {
        this.id = Objects.requireNonNull(id);
        this.name = Objects.requireNonNull(name);
        this.borrowLimit = borrowLimit;
        this.status = MemberStatus.ACTIVE;
        this.activeLoanCount = 0;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public int getBorrowLimit() {
        return borrowLimit;
    }

    public MemberStatus getStatus() {
        return status;
    }

    public int getActiveLoanCount() {
        return activeLoanCount;
    }

    public void suspend() {
        this.status = MemberStatus.SUSPENDED;
    }

    public void activate() {
        this.status = MemberStatus.ACTIVE;
    }

    // Called when a loan is created
    public void incrementLoanCount() {
        if (status == MemberStatus.SUSPENDED) {
            throw new DomainException(DomainException.Code.MEMBER_SUSPENDED, "Member is suspended");
        }
        if (activeLoanCount >= borrowLimit) {
            throw new DomainException(DomainException.Code.BORROW_LIMIT_EXCEEDED, "Borrow limit exceeded");
        }
        activeLoanCount++;
    }

    // Called when a loan is returned
    public void decrementLoanCount() {
        if (activeLoanCount <= 0) {
            throw new DomainException(DomainException.Code.LOAN_ALREADY_RETURNED, "Loan already returned");
        }
        activeLoanCount--;
    }
}