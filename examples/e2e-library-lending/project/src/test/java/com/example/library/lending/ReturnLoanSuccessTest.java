package com.example.library.lending;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ReturnLoanSuccessTest {
    @Test
    void returningActiveLoanUpdatesStateAndCopy() {
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-333", "The Pragmatic Programmer");
        catalog.addTitle(title);
        Copy copy = catalog.createCopy(title.getId());
        MemberService members = new InMemoryMemberService();
        Member member = members.register("Eve");
        LendingService lending = new InMemoryLendingService(catalog, members);
        LocalDate loanDay = LocalDate.of(2024, 2, 1);
        Loan loan = lending.createLoan(member.getId(), copy.getId(), loanDay);
        // return
        LocalDate returnDay = loanDay.plusDays(10);
        lending.returnLoan(loan.getId(), returnDay);
        assertEquals(LoanState.RETURNED, loan.getState());
        assertEquals(returnDay, loan.getReturnDate());
        assertEquals(CopyStatus.AVAILABLE, copy.getStatus());
    }
}
