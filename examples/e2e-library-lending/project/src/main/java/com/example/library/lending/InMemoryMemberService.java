package com.example.library.lending;

import com.example.library.membership.Member;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Simple in‑memory implementation used only by the unit tests.
 * It stores members in a map and re‑uses the domain {@link Member} class.
 */
public class InMemoryMemberService implements MemberService {

    private final Map<String, Member> store = new HashMap<>();

    @Override
    public Member register(String name) {
        String id = UUID.randomUUID().toString();
        Member member = new Member(id, name);
        store.put(id, member);
        return member;
    }

    @Override
    public Member findMember(String memberId) {
        Member m = store.get(memberId);
        if (m == null) {
            throw new IllegalArgumentException("Member not found: " + memberId);
        }
        return m;
    }

    @Override
    public void suspend(String memberId) {
        Member m = findMember(memberId);
        m.suspend();
    }
}
