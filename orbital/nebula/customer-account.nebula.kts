import io.ktor.http.ContentType
import io.ktor.server.request.receiveText
import io.ktor.server.response.respondText

stack {
   http {
      put("/rest/V1/customers/{adobeCustomerId}") { call ->
         val adobeCustomerId = call.parameters["adobeCustomerId"] ?: "missing"
         val requestBody = call.receiveText()
         println("ADOBE_STUB_CAPTURE id=$adobeCustomerId body=$requestBody")
         call.respondText(
            """{ "id": "$adobeCustomerId" }""",
            ContentType.Application.Json
         )
      }

      post("/customer-accounts") { call ->
         val requestBody = call.receiveText()
         println("FWT_STUB_CAPTURE body=$requestBody")
         call.respondText(
            """{ "status": "accepted" }""",
            ContentType.Application.Json
         )
      }
   }
}
