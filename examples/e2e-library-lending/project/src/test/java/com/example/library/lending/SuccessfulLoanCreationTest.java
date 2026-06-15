package com.example.library.lending;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SuccessfulLoanCreationTest {
    @Test
    void loanIsCreatedSuccessfully() {
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-222", "Clean Code");
        catalog.addTitle(title);
        Copy copy = catalog.createCopy(title.getId());
        MemberService members = new InMemoryMemberService();
        Member member = members.register("Dave");
        LendingService lending = new InMemoryLendingService(catalog, members);
        LocalDate today = LocalDate.of(2024, 1, 1);
        Loan loan = lending.createLoan(member.getId(), copy.getId(), today);
        assertEquals(LoanState.ACTIVE, loan.getState());
        assertEquals(today.plusDays(14), loan.getDueDate());
        assertEquals(CopyStatus.ON_LOAN, copy.getStatus());
    }
}
