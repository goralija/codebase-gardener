import { userPath } from "../../../packages/shared/src/routes"

export function renderUserLink(username: string): string {
  return `<a href="${userPath(username)}">${username}</a>`
}
