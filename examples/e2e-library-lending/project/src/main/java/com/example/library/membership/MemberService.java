package com.example.library.membership;

public interface MemberService {
    Member register(String name);
    Member findMember(String id);
    void suspend(String memberId);
}
