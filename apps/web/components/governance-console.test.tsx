import { describe, expect, it } from "vitest";
import { ownerReadinessLabel } from "./governance-console";

const base={assessment_id:"a",assessment_fingerprint:"f",blockers:[],gates:[],live_authorization:"LIVE_AUTHORIZATION_NOT_IMPLEMENTED"};
describe("Owner governance labels",()=>{
  it("never presents a fixture READY state as real Owner readiness",()=>{
    expect(ownerReadinessLabel({...base,status:"READY_FOR_OWNER_LIVE_REVIEW",evidence_origin_summary:{FIXTURE_OAT:1}})).toContain("FIXTURE ONLY");
    expect(ownerReadinessLabel({...base,status:"READY_FOR_OWNER_LIVE_REVIEW",evidence_origin_summary:{REAL_OWNER:1,FIXTURE_OAT:0}})).toBe("READY FOR OWNER REVIEW");
  });
});
