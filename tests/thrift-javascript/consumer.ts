// SPDX-License-Identifier: MIT
import { schema, common, rpc, a, b } from "@proof/thrift-schemas";
const answer: number = new schema.Envelope({ value: new common.Value({answer:42}) }).value.answer;
const first: number = new a.Value({answer:7}).answer;
const second: number = new b.Value({answer:8}).answer;
const call: (delta:number)=>Promise<number> = rpc.Client.prototype.answer;
if (typeof call !== "function" || answer!==42 || first!==7 || second!==8) throw Error("typed schema");
console.log(answer,first,second);
