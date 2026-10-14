import {render, screen, fireEvent} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, expect, it, vi} from "vitest";
import {PackageEnquiry, Pricing} from "../components/Pricing";
import {NavigationProvider} from "../lib/navigation";

afterEach(()=>vi.unstubAllEnvs());
async function prepare() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your name"), "Test contact");
  await user.type(screen.getByLabelText("Company"), "Test organisation");
  await user.type(screen.getByLabelText("Work email"), "person@example.com");
  await user.type(screen.getByLabelText("Questions or companies to explore"), "Compare workforce training across our peers.");
  await user.click(screen.getByRole("button", {name:/Prepare request/}));
  return user;
}
it("carries the package choice from pricing into an enquiry", async()=>{
  window.history.replaceState(null,"","/pricing");
  render(<NavigationProvider><Pricing/></NavigationProvider>);
  const link = screen.getByRole("link",{name:/Request sector intelligence/});
  expect(link).toHaveAttribute("href","/contact?package=sector");
  await userEvent.setup().click(link);
  expect(window.location.search).toBe("?package=sector");
});
it("prepares an editable request without claiming submission or sending data",async()=>{
  vi.stubEnv("VITE_SALES_EMAIL", "");
  window.history.replaceState(null,"","/contact?package=sector");
  const fetch=vi.fn();vi.stubGlobal("fetch",fetch);
  render(<NavigationProvider><PackageEnquiry/></NavigationProvider>);
  expect(screen.getByRole("combobox")).toHaveValue("sector");
  const user=await prepare();
  expect(screen.getByRole("status")).toHaveTextContent("Not sent");
  expect(screen.getByRole("button",{name:/Download request/})).toBeInTheDocument();
  expect(screen.queryByRole("link",{name:/Open email draft/})).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button",{name:"Edit request"}));
  expect(screen.getByLabelText("Work email")).toHaveValue("person@example.com");
});
it("uses only the configured recipient and encodes the email body",async()=>{
  window.history.replaceState(null,"","/contact?package=company");
  render(<NavigationProvider><PackageEnquiry salesEmail="sales@example.com"/></NavigationProvider>);await prepare();
  const href=screen.getByRole("link",{name:/Open email draft/}).getAttribute("href")!;
  expect(href.startsWith("mailto:sales@example.com?subject=")).toBe(true);
  expect(decodeURIComponent(href)).toContain("Compare workforce training");
  expect(screen.getByRole("status")).toHaveTextContent("Not sent");
});
it("requires contact fields before a request is prepared",()=>{
  window.history.replaceState(null,"","/contact");
  render(<NavigationProvider><PackageEnquiry/></NavigationProvider>);
  const email=screen.getByLabelText("Work email") as HTMLInputElement;
  expect(email.required).toBe(true);expect(email.checkValidity()).toBe(false);
  fireEvent.change(email,{target:{value:"not-an-email"}});expect(email.checkValidity()).toBe(false);
});
