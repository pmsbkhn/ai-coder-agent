package com.example.library.lending;

import com.example.library.common.DomainException;
import com.example.library.membership.MemberStatus;
import java.time.LocalDate;
import java.util.Objects;

public class Loan {
    private final String id;
    private final String memberId;
    private final String copyId;
    private final LocalDate loanDate;
    private final LocalDate dueDate;
    private LoanState state;
    private LocalDate returnDate;

    public Loan(String id, String memberId, String copyId, LocalDate loanDate, LocalDate dueDate) {
        this.id = id;
        this.memberId = memberId;
        this.copyId = copyId;
        this.loanDate = loanDate;
        this.dueDate = dueDate;
        this.state = LoanState.ACTIVE;
        this.returnDate = null;
    }

    public String getId() {
        return id;
    }

    public String getMemberId() {
        return memberId;
    }

    public String getCopyId() {
        return copyId;
    }

    public LocalDate getLoanDate() {
        return loanDate;
    }

    public LocalDate getDueDate() {
        return dueDate;
    }

    public LoanState getState() {
        return state;
    }

    public LocalDate getReturnDate() {
        return returnDate;
    }

    public boolean isOverdue(LocalDate today) {
        if (state == LoanState.RETURNED || state == LoanState.OVERDUE) {
            return false;
        }
        return today.isAfter(dueDate);
    }

    // This method should only be called by the LendingService when returning a loan
    public void returnLoanInPlace(LocalDate returnDate) {
        if (state == LoanState.RETURNED) {
            throw new DomainException(DomainException.Code.LOAN_ALREADY_RETURNED, "Loan already returned");
        }
        this.state = LoanState.RETURNED;
        setReturnDate(returnDate);
    }

    // For overdue status
    public void markAsOverdueInPlace() {
        if (state == LoanState.RETURNED) {
            throw new DomainException(DomainException.Code.LOAN_ALREADY_RETURNED, "Loan already returned");
        }
        this.state = LoanState.OVERDUE;
    }

    // make returnDate mutable – add a setter (package-private)
    void setReturnDate(LocalDate date) { this.returnDate = date; }
}
