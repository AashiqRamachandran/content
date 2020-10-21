Generic webhook to be triggered in order to create incident.

## Configure Generic Webhook on Cortex XSOAR

1. Navigate to **Settings** > **Integrations** > **Servers & Services**.
2. Search for Generic Webhook.
3. Click **Add instance** to create and configure a new integration instance.

| **Parameter** | **Description** | **Required** |
| --- | --- | --- |
| longRunningPort | Listen Port | True |
| username | Username (see [Security](#security) for more details) | False |
| password | Password (see [Security](#security) for more details) | False |
| certificate | Certificate (Required for HTTPS, in case not using the server rerouting) | False |
| key | Private Key (Required for HTTPS, in case not using the server rerouting) | False |
| incidentType | Incident type | False |

4. Click **Done**.
5. Navigate to  **Settings > About > Troubleshooting**.
6. In the **Server Configuration** section, verify that the ***instance.execute.external.\<INTEGRATION-INSTANCE-NAME\>*** key is set to *true*. If this key does not exist, click **+ Add Server Configuration** and add the *instance.execute.external.\<INTEGRATION-INSTANCE-NAME\>* and set the value to *true*. See the following [reference article](https://xsoar.pan.dev/docs/reference/articles/long-running-invoke) for further information.

You can now trigger the webhook URL: `<CORTEX-XSOAR-URL>/instance/execute/<INTEGRATION-INSTANCE-NAME>`, e.g. `https://my.demisto.live/instance/execute/webhook`

**Note**: The ***Listen Port*** needs to be available, which means it has to be unique per integration instance, and cannot be used by other long-running integrations.

## Usage
The Generic Webhook accepts POST HTTP queries, with the following optional fields in the request body:

| **Field** | **Type** | **Description** |
| --- | --- | --- |
| name | string | Name of the incident to be created. |
| type | string | Type of the incident to be created. If not provided, the value of the integration parameter ***Incident type*** will be taken.  |
| occurred | string | Occurred date of the incident to be created in ISO-8601 format. If not provided, the trigger time will be taken. |
| raw_json | object | Details of the incident to be created, e.g. `{"field1":"value1","field2":"value2"}` |

For example, triggering the webhook using cURL:

`curl -POST https://my.demisto.live/instance/execute/webhook -H "Authorization: token" -d '{"name":"incident created via generic webhook","raw_json":{"some_field":"some_value"}}'`

The response will be an array containing an object with the created incident metadata, such as the incident ID.

## Security
- To validate an incident request creation, you can the Username/Password integration parameters for one of the following:
     * Basic authentication
     * Verification token given in a request header, by setting the username to `_header:<HEADER-NAME>` and the password to be the header value. 
     
        For example, if the request include in the `Authorization` header the value `Bearer XXX`, then the username should be set to `_header:Authorization` and the password should be set to `Bearer XXX`.
    
- In case you're not using the server rerouting as described above, you can configure an HTTPS server by providing certificate and private key.